package com.matrix.prp.finance.imports;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

/**
 * Tenant-scoped source link lookups. A bounded single SQL round trip per
 * chunk replaces per-row preview queries; committing still rechecks each
 * candidate inside the original FOR UPDATE transaction.
 */
@Repository
public class FinanceImportSourceLinkRepository {
    // Limit derived-table terms and bind parameters independently of file size.
    static final int PREVIEW_CHUNK_SIZE = 250;
    private final JdbcTemplate jdbc;

    public FinanceImportSourceLinkRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /**
     * Returns original submitted IDs (not DB canonicalized IDs).
     * The join uses MySQL's existing source_transaction_id column collation,
     * which is important for matching e.g. differently cased exported IDs.
     */
    Set<String> findPostedPreviewIds(long owner, List<WeChatBillParser.BillRow> rows) {
        LinkedHashSet<String> candidateIds = new LinkedHashSet<>();
        for (var row : rows) {
            if (!row.sourceTransactionId().isBlank()) {
                candidateIds.add(row.sourceTransactionId());
            }
        }
        if (candidateIds.isEmpty()) return Set.of();
        List<String> ids = new ArrayList<>(candidateIds);
        Set<String> found = new java.util.HashSet<>();
        for (int i = 0; i < ids.size(); i += PREVIEW_CHUNK_SIZE) {
            List<String> chunk = ids.subList(i, Math.min(i + PREVIEW_CHUNK_SIZE, ids.size()));
            QueryBatch batch = plan(owner, chunk);
            found.addAll(jdbc.queryForList(batch.sql(), String.class, batch.bindings().toArray()));
        }
        return found;
    }

    boolean alreadyPosted(long owner, String transactionId) {
        Integer count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM prp_finance_source_links " +
            "WHERE user_id=? AND platform='WECHAT' AND source_transaction_id=?",
            Integer.class, owner, transactionId);
        return count != null && count > 0;
    }

    /**
     * The left side is the exact uploaded ID, not the stored source ID.
     * Both input and owner are bound parameters, never interpolated SQL.
     * EXISTS avoids duplicate output even if an unexpected table row exists.
     */
    static QueryBatch plan(long owner, List<String> ids) {
        if (ids.isEmpty() || ids.size() > PREVIEW_CHUNK_SIZE) {
            throw new IllegalArgumentException("Unbounded import lookup batch");
        }
        StringBuilder sql = new StringBuilder("SELECT submitted.source_id FROM (");
        List<Object> params = new ArrayList<>(ids.size() + 1);
        for (int i = 0; i < ids.size(); i++) {
            if (i > 0) sql.append(" UNION ALL ");
            sql.append(i == 0 ? "SELECT ? AS source_id" : "SELECT ?");
            params.add(ids.get(i));
        }
        sql.append(") AS submitted WHERE EXISTS (" +
            "SELECT 1 FROM prp_finance_source_links AS links " +
            "WHERE links.user_id=? AND links.platform='WECHAT' " +
            "AND links.source_transaction_id=submitted.source_id)");
        params.add(owner);
        return new QueryBatch(sql.toString(), List.copyOf(params));
    }

    record QueryBatch(String sql, List<Object> bindings) {}
}
