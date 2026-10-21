package com.matrix.prp.finance.imports;

import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.finance.entity.FinanceAccountEntity;
import com.matrix.prp.finance.entity.FinanceTransactionEntity;
import com.matrix.prp.finance.mapper.FinanceAccountMapper;
import com.matrix.prp.finance.mapper.FinanceTransactionMapper;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.context.annotation.Profile;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@Service
@Profile("!test")
public class FinanceImportService {
    private static final int MAX_BYTES = 5 * 1024 * 1024;
    private final JdbcTemplate jdbc;
    private final FinanceAccountMapper accounts;
    private final FinanceTransactionMapper transactions;
    private final WeChatBillParser parser;
    private final FinanceImportSourceLinkRepository sourceLinks;

    public FinanceImportService(JdbcTemplate jdbc, FinanceAccountMapper accounts,
                                FinanceTransactionMapper transactions, WeChatBillParser parser,
                                FinanceImportSourceLinkRepository sourceLinks) {
        this.jdbc=jdbc; this.accounts=accounts; this.transactions=transactions;
        this.parser=parser; this.sourceLinks=sourceLinks;
    }

    public record RowView(long id,int sourceLine,LocalDateTime transactionAt,String transactionType,
                          String counterparty,String description,String direction,BigDecimal amount,
                          String paymentMethod,String originalStatus,String sourceTransactionId,
                          String rowStatus) {}
    public record BatchView(long id,String platform,String sourceAccountKey,String filename,String status,
                            long ready,long review,long duplicate,long posted,List<RowView> rows) {}
    public record CommitRequest(Map<String,Long> paymentAccounts) {}
    public record HistoryItem(long id,String platform,String sourceAccountKey,String filename,
                              String status,LocalDateTime createdAt) {}

    @Transactional
    public BatchView preview(MultipartFile file,String sourceAccountOverride) {
        if (file==null || file.isEmpty() || file.getSize()>MAX_BYTES
                || file.getOriginalFilename()==null
                || !file.getOriginalFilename().toLowerCase(java.util.Locale.ROOT).endsWith(".xlsx"))
            throw bad("A WeChat XLSX up to 5MB is required");
        byte[] bytes;
        try { bytes=file.getBytes(); }
        catch (Exception e) { throw bad("Could not read XLSX"); }
        var bill=parser.parse(bytes);
        long owner=CurrentUser.id();
        String source=FinanceImportPolicy.sourceAccountKey(sourceAccountOverride,bill.sourceAccount());
        final String safeFileName=FinanceImportPolicy.safeOriginalFilename(file.getOriginalFilename());
        String digest;
        try { digest=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); }
        catch (Exception e) { throw new IllegalStateException("SHA-256 unavailable",e); }
        List<Long> differentSource=jdbc.query(
            "SELECT id FROM prp_finance_import_batches WHERE user_id=? AND platform='WECHAT' AND sha256=? AND source_account_key<>?",
            (rs,n)->rs.getLong(1),owner,digest,source);
        if(!differentSource.isEmpty()) throw bad("Same file was already uploaded for another source account");
        List<Long> existing=jdbc.query(
            "SELECT id FROM prp_finance_import_batches WHERE user_id=? AND platform='WECHAT' AND source_account_key=? AND sha256=?",
            (rs,n)->rs.getLong(1),owner,source,digest);
        if(!existing.isEmpty()) return detail(existing.get(0));
        KeyHolder key=new GeneratedKeyHolder();
        String sourceKey=source;
        jdbc.update(conn->{
            var ps=conn.prepareStatement("INSERT INTO prp_finance_import_batches "
                +"(user_id,platform,source_account_key,original_filename,sha256,status,created_at,updated_at) "
                +"VALUES (?,'WECHAT',?,?,?,'DRAFT',NOW(6),NOW(6))",
                java.sql.Statement.RETURN_GENERATED_KEYS);
            ps.setLong(1,owner);ps.setString(2,sourceKey);ps.setString(3,safeFileName);ps.setString(4,digest);
            return ps;
        },key);
        long batch=Objects.requireNonNull(key.getKey()).longValue();
        // Snapshot-style advisory classification; source-link uniqueness and
        // the commit-time recheck remain the authoritative posting defenses.
        Set<String> postedIds=sourceLinks.findPostedPreviewIds(owner,bill.rows());
        Set<String> seen=new HashSet<>();
        for(var row:bill.rows()) {
            String status=FinanceImportPolicy.previewRowStatus(
                row.reviewState(),row.sourceTransactionId(),seen,
                ()->postedIds.contains(row.sourceTransactionId()));
            jdbc.update("INSERT INTO prp_finance_import_rows "
                +"(batch_id,user_id,source_line,source_transaction_id,merchant_transaction_id,transaction_at,"
                +"transaction_type,counterparty,description,direction,amount,payment_method,original_status,note,"
                +"row_status,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NOW(6))",
                batch,owner,row.sourceLine(),row.sourceTransactionId(),row.merchantTransactionId(),
                row.transactionAt(),row.transactionType(),row.counterparty(),row.description(),
                row.direction(),row.amount(),row.paymentMethod(),row.originalStatus(),row.note(),status);
        }
        return detail(batch);
    }

    /** These are only candidates. REVIEW and DUPLICATE rows cannot reach the ledger. */
    @Transactional
    public BatchView commit(long batchId, CommitRequest command) {
        long owner=CurrentUser.id();
        // Lock the batch to serialize repeated clicks from the same user.
        var locks=jdbc.query("SELECT id FROM prp_finance_import_batches WHERE id=? AND user_id=? FOR UPDATE",
            (rs,n)->rs.getLong(1),batchId,owner);
        if(locks.isEmpty()) throw notFound();
        Map<String,Long> mappings=command==null || command.paymentAccounts()==null
            ? Map.of() : command.paymentAccounts();
        Map<Long,FinanceAccountEntity> ownedAccounts=new HashMap<>();
        for(var entry:mappings.entrySet()) {
            if(entry.getKey()==null || entry.getValue()==null || entry.getKey().length()>128)
                throw bad("Invalid payment method mapping");
            FinanceAccountEntity account=accounts.selectById(entry.getValue());
            ownedAccounts.put(entry.getValue(),FinanceImportPolicy.requireOwnedCnyAccount(account,owner));
        }
        var batchInfo=jdbc.query("SELECT source_account_key FROM prp_finance_import_batches WHERE id=? AND user_id=?",
            (rs,n)->rs.getString(1),batchId,owner);
        String source=batchInfo.get(0);
        var candidates=jdbc.query("SELECT id,source_transaction_id,transaction_at,transaction_type,counterparty,"
                +"description,direction,amount,payment_method,original_status,row_status "
                +"FROM prp_finance_import_rows WHERE batch_id=? AND user_id=? AND row_status='READY' ORDER BY id FOR UPDATE",
            (rs,n)->new Candidate(rs.getLong(1),rs.getString(2),rs.getTimestamp(3).toLocalDateTime(),
                rs.getString(4),rs.getString(5),rs.getString(6),rs.getString(7),
                rs.getBigDecimal(8),rs.getString(9),rs.getString(10)),batchId,owner);
        for(var row:candidates) {
            Long accountId=mappings.get(row.paymentMethod());
            if(accountId==null) continue; // Never guess which wallet/bank funded a payment.
            if(sourceLinks.alreadyPosted(owner,row.sourceId())) {
                jdbc.update("UPDATE prp_finance_import_rows SET row_status='DUPLICATE' WHERE id=? AND user_id=?",
                    row.id(),owner);
                continue;
            }
            FinanceAccountEntity account=ownedAccounts.get(accountId);
            FinanceTransactionEntity ledger=FinanceImportPolicy.newPostedExpense(
                owner,account,row.amount(),row.counterparty(),row.description(),
                row.at(),LocalDateTime.now());
            transactions.insert(ledger);
            // Same DB transaction: if the unique identity collides, the entire ledger insertion rolls back.
            jdbc.update("INSERT INTO prp_finance_source_links "
                +"(user_id,platform,source_account_key,source_transaction_id,import_row_id,finance_transaction_id,created_at)"
                +" VALUES (?,'WECHAT',?,?,?,?,NOW(6))",
                owner,source,row.sourceId(),row.id(),ledger.getId());
            jdbc.update("UPDATE prp_finance_import_rows SET row_status='POSTED',finance_transaction_id=? "
                +"WHERE id=? AND user_id=?",ledger.getId(),row.id(),owner);
        }
        jdbc.update("UPDATE prp_finance_import_batches SET status="
            +"CASE WHEN (SELECT COUNT(*) FROM prp_finance_import_rows WHERE batch_id=? AND row_status='READY')=0 "
            +"THEN 'DONE' ELSE 'PARTIAL' END,updated_at=NOW(6) WHERE id=? AND user_id=?",
            batchId,batchId,owner);
        return detail(batchId);
    }
    private record Candidate(long id,String sourceId,LocalDateTime at,String type,String counterparty,
                             String description,String direction,BigDecimal amount,String paymentMethod,String originalStatus) {}

    public List<HistoryItem> history() {
        return jdbc.query("SELECT id,platform,source_account_key,original_filename,status,created_at "
            +"FROM prp_finance_import_batches WHERE user_id=? ORDER BY id DESC LIMIT 20",
            (rs,n)->new HistoryItem(rs.getLong(1),rs.getString(2),rs.getString(3),rs.getString(4),
                rs.getString(5),rs.getTimestamp(6).toLocalDateTime()),CurrentUser.id());
    }

    public BatchView detail(long batchId) {
        long owner=CurrentUser.id();
        var matches=jdbc.query("SELECT platform,source_account_key,original_filename,status "
                +"FROM prp_finance_import_batches WHERE id=? AND user_id=?",
            (rs,n)->new String[]{rs.getString(1),rs.getString(2),rs.getString(3),rs.getString(4)},
            batchId,owner);
        if(matches.isEmpty()) throw notFound();
        var rows=jdbc.query("SELECT id,source_line,transaction_at,transaction_type,counterparty,description,"
                +"direction,amount,payment_method,original_status,source_transaction_id,row_status "
                +"FROM prp_finance_import_rows WHERE batch_id=? AND user_id=? ORDER BY source_line",
            (rs,n)->new RowView(rs.getLong(1),rs.getInt(2),rs.getTimestamp(3).toLocalDateTime(),
                rs.getString(4),rs.getString(5),rs.getString(6),rs.getString(7),rs.getBigDecimal(8),
                rs.getString(9),rs.getString(10),rs.getString(11),rs.getString(12)),batchId,owner);
        long ready=rows.stream().filter(r->"READY".equals(r.rowStatus())).count();
        long review=rows.stream().filter(r->"REVIEW".equals(r.rowStatus())).count();
        long duplicate=rows.stream().filter(r->"DUPLICATE".equals(r.rowStatus())).count();
        long posted=rows.stream().filter(r->"POSTED".equals(r.rowStatus())).count();
        var b=matches.get(0);
        return new BatchView(batchId,b[0],b[1],b[2],b[3],ready,review,duplicate,posted,rows);
    }

    private ResponseStatusException bad(String message) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST,message);
    }
    private ResponseStatusException notFound() {
        return new ResponseStatusException(HttpStatus.NOT_FOUND,"Import batch not found");
    }
}
