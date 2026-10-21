package com.matrix.prp;

import static org.assertj.core.api.Assertions.*;
import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.finance.imports.FinanceImportService;
import com.matrix.prp.finance.imports.FinanceImportStagingRepository;
import com.matrix.prp.finance.imports.WeChatBillParser;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.dao.DataAccessException;
import com.matrix.prp.finance.mapper.FinanceAccountMapper;
import com.matrix.prp.finance.entity.FinanceAccountEntity;
import java.io.ByteArrayOutputStream;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.web.server.ResponseStatusException;

@SpringBootTest
@ActiveProfiles("video-integration")
class FinanceImportDatabaseIT {
    @Autowired FinanceImportService imports;
    @Autowired FinanceAccountMapper accounts;
    @Autowired FinanceImportStagingRepository staging;
    @Autowired JdbcTemplate jdbc;
    @Autowired PlatformTransactionManager transactionManager;

    private void owner(long id) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(new UserProfile(id,"fixture","Test Owner"),null,List.of()));
    }

    private byte[] sample(String id) throws Exception {
        try (var excel=new XSSFWorkbook(); var stream=new ByteArrayOutputStream()) {
            var sheet=excel.createSheet();
            sheet.createRow(1).createCell(0).setCellValue("微信昵称：[Fixture]");
            var header=sheet.createRow(17);
            String[] h={"交易时间","交易类型","交易对方","商品","收/支","金额(元)",
                "支付方式","当前状态","交易单号","商户单号","备注"};
            for(int i=0;i<h.length;i++)header.createCell(i).setCellValue(h[i]);
            String[][] rows={
                {"2026-10-14 00:24:20","商户消费","Fixture Shop","meal","支出","36.70","零钱","支付成功","45"+id,"a","/"},
                {"2026-10-14 00:25:20","商户消费","Fixture Shop","refund","支出","9.00","零钱","已全额退款","46"+id,"b","/"},
                {"2026-10-14 00:26:20","转账","Fixture Contact","transfer","支出","100.00","零钱","对方已收钱","47"+id,"c","/"}
            };
            for(int n=0;n<rows.length;n++) {
                var row=sheet.createRow(18+n);
                for(int c=0;c<h.length;c++)row.createCell(c).setCellValue(rows[n][c]);
            }
            excel.write(stream);
            return stream.toByteArray();
        }
    }

    private byte[] bulkSample(String id, int count) throws Exception {
        try (var excel = new XSSFWorkbook(); var out = new ByteArrayOutputStream()) {
            var sheet = excel.createSheet();
            sheet.createRow(1).createCell(0).setCellValue("微信昵称：[Fixture]");
            var header = sheet.createRow(17);
            String[] columns = {"交易时间","交易类型","交易对方","商品","收/支",
                "金额(元)","支付方式","当前状态","交易单号","商户单号","备注"};
            for(int i=0;i<columns.length;i++)header.createCell(i).setCellValue(columns[i]);
            for(int i=0;i<count;i++) {
                var r=sheet.createRow(18+i);
                String[] cells = {"2026-10-14 00:24:20",
                    i==450 ? "转账" : "商户消费", "Synthetic Shop",
                    "item-"+i, "支出","10.50","零钱",
                    i==450 ? "对方已收钱" : "支付成功",
                    i==501 ? "id-"+id+"-5" : "id-"+id+"-"+i, "merchant","test"};
                for(int j=0;j<cells.length;j++)r.createCell(j).setCellValue(cells[j]);
            }
            excel.write(out);
            return out.toByteArray();
        }
    }

    @Test void batchedStagingPersistsAllRowsInOriginalOrderAndReviewsUncertain() throws Exception {
        long accountOwner=8023701L;
        String id=UUID.randomUUID().toString().replace("-","");
        owner(accountOwner);
        try {
            byte[] data=bulkSample(id,510);
            var file=new MockMultipartFile("file","bulk.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",data);
            var batch=imports.preview(file,null);
            assertThat(batch.rows()).hasSize(510);
            assertThat(batch.ready()).isEqualTo(508);
            assertThat(batch.review()).isEqualTo(1);
            assertThat(batch.duplicate()).isEqualTo(1);
            assertThat(batch.rows().get(0).sourceLine()).isEqualTo(19);
            assertThat(batch.rows().get(249).sourceLine()).isEqualTo(268);
            assertThat(batch.rows().get(250).sourceLine()).isEqualTo(269);
            assertThat(batch.rows().get(500).sourceLine()).isEqualTo(519);
            assertThat(batch.rows().get(501).rowStatus()).isEqualTo("DUPLICATE");
            assertThat(batch.rows().get(450).rowStatus()).isEqualTo("REVIEW");
            assertThat(imports.preview(file,null).id()).isEqualTo(batch.id());
            owner(8023702L);
            assertThatThrownBy(()->imports.detail(batch.id()))
                .isInstanceOf(ResponseStatusException.class);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    @Test void secondChunkConstraintFailureRollsBackHeaderAndEveryEarlierRow() {
        final long userId=8023801L;
        final String nonce=UUID.randomUUID().toString().replace("-","");
        var rows=new java.util.ArrayList<FinanceImportStagingRepository.StagedRow>();
        for(int i=1;i<=250;i++) {
            rows.add(new FinanceImportStagingRepository.StagedRow(
                syntheticRow(i,"external-"+nonce+"-"+i),"READY"));
        }
        // A repeated source_line violates the existing V21 unique
        // (batch_id,source_line) AFTER the first JDBC batch succeeds.
        rows.add(new FinanceImportStagingRepository.StagedRow(
            syntheticRow(1,"external-"+nonce+"-dupe"),"READY"));
        var tx=new TransactionTemplate(transactionManager);
        assertThatThrownBy(()->tx.executeWithoutResult(ignore->{
            jdbc.update("INSERT INTO prp_finance_import_batches " +
                "(user_id,platform,source_account_key,original_filename,sha256,status,created_at,updated_at) " +
                "VALUES (?,'WECHAT',?,?,?,'DRAFT',NOW(6),NOW(6))",
                userId,"synthetic-"+nonce,"bulk.xlsx",
                "a".repeat(64));
            Long batch=jdbc.queryForObject("SELECT LAST_INSERT_ID()", Long.class);
            staging.insertRows(batch,userId,rows);
        })).isInstanceOf(DataAccessException.class);
        assertThat(jdbc.queryForObject(
            "SELECT COUNT(*) FROM prp_finance_import_batches WHERE user_id=? AND source_account_key=?",
            Integer.class,userId,"synthetic-"+nonce)).isZero();
        assertThat(jdbc.queryForObject(
            "SELECT COUNT(*) FROM prp_finance_import_rows WHERE user_id=? AND source_transaction_id LIKE ?",
            Integer.class,userId,"external-"+nonce+"-%")).isZero();
    }

    private WeChatBillParser.BillRow syntheticRow(int line, String sourceId) {
        return new WeChatBillParser.BillRow(line,
            LocalDateTime.of(2026,10,14,0,24,20),"商户消费","Synthetic Shop",
            "item","支出",new BigDecimal("10.50"),"零钱","支付成功",
            sourceId,"merchant","test","READY");
    }

    @Test void batchingKeepsSourceCollationAndTenantIsolation() throws Exception {
        // The V21 source-link unique key uses utf8mb4_unicode_ci; Java
        // String.equalsIgnoreCase is not a sufficient substitute for SQL.
        long alice = 8023601L, bob = 8023602L;
        String id = "abc" + UUID.randomUUID().toString().replace("-", "");
        var lowerUpload = new MockMultipartFile("file", "original.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", sample(id));
        var upperUpload = new MockMultipartFile("file", "changedcase.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            sample(id.toUpperCase(java.util.Locale.ROOT)));
        try {
            owner(alice);
            var account = new FinanceAccountEntity();
            account.setUserId(alice); account.setName("review-" + id);
            account.setType("cash"); account.setCurrency("CNY");
            account.setOpeningBalance(BigDecimal.valueOf(100));
            account.setCreatedAt(LocalDateTime.now());
            account.setUpdatedAt(account.getCreatedAt());
            account.setDeleted(0); account.setNote("test");
            accounts.insert(account);
            var first = imports.preview(lowerUpload, null);
            assertThat(first.ready()).isEqualTo(1);
            assertThat(imports.commit(first.id(),
                new FinanceImportService.CommitRequest(Map.of("零钱", account.getId()))).posted())
                .isEqualTo(1);
            // Same external transaction, different case and XLSX bytes;
            // the database collation should still classify a duplicate.
            var alreadyLinked = imports.preview(upperUpload, null);
            assertThat(alreadyLinked.ready()).isZero();
            assertThat(alreadyLinked.duplicate()).isEqualTo(1);
            assertThat(alreadyLinked.review()).isEqualTo(2);
            assertThat(imports.commit(alreadyLinked.id(),
                new FinanceImportService.CommitRequest(Map.of("零钱", account.getId()))).posted())
                .isZero();
            // A separate user is allowed to import their OWN external ID.
            owner(bob);
            var independent = imports.preview(upperUpload, null);
            assertThat(independent.ready()).isEqualTo(1);
            assertThat(independent.duplicate()).isZero();
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    @Test void importsSafeExpenseOnlyAndRefusesCrossUserOrRepeat() throws Exception {
        long first=8023501L,second=8023502L;
        String id=UUID.randomUUID().toString().replace("-","");
        byte[] bytes=sample(id);
        var upload=new MockMultipartFile("file","wechat.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",bytes);
        owner(first);
        var account=new FinanceAccountEntity();
        account.setUserId(first);account.setName("import-test-"+id);account.setType("cash");
        account.setCurrency("CNY");account.setOpeningBalance(BigDecimal.valueOf(100));
        account.setCreatedAt(LocalDateTime.now());account.setUpdatedAt(account.getCreatedAt());
        account.setDeleted(0);account.setNote("test");
        accounts.insert(account);
        var preview=imports.preview(upload,null);
        assertThat(preview.ready()).isEqualTo(1);
        assertThat(preview.review()).isEqualTo(2);
        assertThat(preview.posted()).isZero();
        assertThat(imports.preview(upload,null).id()).isEqualTo(preview.id());
        var command=new FinanceImportService.CommitRequest(Map.of("零钱",account.getId()));
        var done=imports.commit(preview.id(),command);
        assertThat(done.ready()).isZero();
        assertThat(done.review()).isEqualTo(2);
        assertThat(done.posted()).isEqualTo(1);
        assertThat(imports.commit(preview.id(),command).posted()).isEqualTo(1);
        assertThatThrownBy(()->imports.preview(upload,"another-source"))
            .isInstanceOf(ResponseStatusException.class);
        owner(second);
        assertThatThrownBy(()->imports.detail(preview.id()))
            .isInstanceOf(ResponseStatusException.class);
        assertThatThrownBy(()->imports.commit(preview.id(),command))
            .isInstanceOf(ResponseStatusException.class);
        SecurityContextHolder.clearContext();
    }
}
