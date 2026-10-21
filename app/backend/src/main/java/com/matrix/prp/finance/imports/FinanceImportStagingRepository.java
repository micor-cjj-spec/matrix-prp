package com.matrix.prp.finance.imports;

import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.BatchPreparedStatementSetter;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

/**
 * Persists a previously classified import preview. Call only inside the
 * FinanceImportService.preview transaction; a failed chunk must roll back
 * the entire batch header and all earlier rows.
 */
@Repository
@Profile("!test")
public class FinanceImportStagingRepository {
    static final int INSERT_CHUNK_SIZE = 250;
    private static final String INSERT_SQL =
        "INSERT INTO prp_finance_import_rows " +
        "(batch_id,user_id,source_line,source_transaction_id,merchant_transaction_id,transaction_at," +
        "transaction_type,counterparty,description,direction,amount,payment_method,original_status,note," +
        "row_status,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NOW(6))";

    private final JdbcTemplate jdbc;

    public FinanceImportStagingRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record StagedRow(WeChatBillParser.BillRow source, String rowStatus) {}

    public void insertRows(long batchId, long owner, List<StagedRow> entries) {
        for (int offset = 0; offset < entries.size(); offset += INSERT_CHUNK_SIZE) {
            List<StagedRow> chunk = entries.subList(
                offset, Math.min(offset + INSERT_CHUNK_SIZE, entries.size()));
            int[] counts = jdbc.batchUpdate(INSERT_SQL, new BatchPreparedStatementSetter() {
                @Override
                public int getBatchSize() {
                    return chunk.size();
                }

                @Override
                public void setValues(PreparedStatement ps, int i) throws SQLException {
                    StagedRow item = chunk.get(i);
                    WeChatBillParser.BillRow row = item.source();
                    ps.setLong(1, batchId);
                    ps.setLong(2, owner);
                    ps.setInt(3, row.sourceLine());
                    ps.setString(4, row.sourceTransactionId());
                    ps.setString(5, row.merchantTransactionId());
                    ps.setObject(6, row.transactionAt());
                    ps.setString(7, row.transactionType());
                    ps.setString(8, row.counterparty());
                    ps.setString(9, row.description());
                    ps.setString(10, row.direction());
                    ps.setBigDecimal(11, row.amount());
                    ps.setString(12, row.paymentMethod());
                    ps.setString(13, row.originalStatus());
                    ps.setString(14, row.note());
                    ps.setString(15, item.rowStatus());
                }
            });
            // Some JDBC drivers return SUCCESS_NO_INFO (-2) for a successful
            // batch. Never accept EXECUTE_FAILED (-3), zero or a short result.
            if (counts == null || counts.length != chunk.size()) {
                throw new IllegalStateException("Import staging insert count mismatch");
            }
            for (int count : counts) {
                if (count != 1 && count != Statement.SUCCESS_NO_INFO) {
                    throw new IllegalStateException("Import staging row not inserted");
                }
            }
        }
    }
}
