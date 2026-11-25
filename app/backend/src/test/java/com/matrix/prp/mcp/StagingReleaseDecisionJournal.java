package com.matrix.prp.mcp;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.HexFormat;
import java.util.UUID;
import java.util.function.LongSupplier;

import static com.matrix.prp.mcp.StagingReleaseApprovalBoundary.*;

/** Disposable CI-only MySQL journal, not part of the application schema or jar. */
final class StagingReleaseDecisionJournal implements DecisionJournal {
    private static final String URL = "jdbc:mysql://127.0.0.1:3306/matrix_prp?connectTimeout=3000&socketTimeout=5000";
    private static final int CAPACITY = 128;
    private final String state;
    private final String receipts;

    StagingReleaseDecisionJournal(String suffix) {
        if (suffix == null || !suffix.matches("[0-9a-f]{32}"))
            throw new IllegalArgumentException("INVALID_TEST_TABLE_SUFFIX");
        state = "p35_ci_state_" + suffix;
        receipts = "p35_ci_receipt_" + suffix;
    }

    static String newSuffix() { return UUID.randomUUID().toString().replace("-", ""); }

    static Connection open() throws SQLException {
        // Fixed disposable GitHub Actions service credentials, not a configurable
        // production connection. Explicit opt-in is only set on the CI test step.
        if (!"true".equals(System.getenv("GITHUB_ACTIONS"))
                || !"1".equals(System.getenv("PRP_P35_DISPOSABLE_MYSQL")))
            throw new IllegalStateException("DISPOSABLE_CI_DATABASE_REQUIRED");
        Connection c = DriverManager.getConnection(URL, "matrix_prp", "ci-app-password");
        try (var stmt = c.createStatement();
             var rs = stmt.executeQuery("SELECT DATABASE(), CURRENT_USER()")) {
            if (!rs.next() || !"matrix_prp".equals(rs.getString(1))
                    || !rs.getString(2).startsWith("matrix_prp@"))
                throw new SQLException("UNEXPECTED_DISPOSABLE_DATABASE");
            return c;
        } catch (SQLException | RuntimeException e) {
            c.close();
            throw e;
        }
    }

    void initialize() throws SQLException {
        try (var c = open(); var s = c.createStatement()) {
            s.execute("CREATE TABLE " + state +
                " (id INT PRIMARY KEY, last_time BIGINT NOT NULL, total INT NOT NULL) ENGINE=InnoDB");
            s.execute("INSERT INTO " + state + " VALUES (1,0,0)");
            s.execute("CREATE TABLE " + receipts +
                " (approval_id CHAR(36) PRIMARY KEY, nonce CHAR(36) NOT NULL UNIQUE," +
                " decision VARCHAR(8) NOT NULL, proof_digest CHAR(64) NOT NULL," +
                " recorded_at BIGINT NOT NULL) ENGINE=InnoDB");
        }
    }

    void cleanup() throws SQLException {
        try (var c = open(); var s = c.createStatement()) {
            s.execute("DROP TABLE IF EXISTS " + receipts);
            s.execute("DROP TABLE IF EXISTS " + state);
        }
    }

    @Override public void record(Pending pending, Envelope envelope, LongSupplier lockedRecheck) {
        try (var c = open()) {
            c.setAutoCommit(false);
            try {
                long last;
                int count;
                try (var s = c.prepareStatement("SELECT last_time,total FROM " + state + " WHERE id=1 FOR UPDATE");
                     var rs = s.executeQuery()) {
                    if (!rs.next()) throw new SQLException("MISSING_TEST_JOURNAL");
                    last = rs.getLong(1);
                    count = rs.getInt(2);
                }
                long now = lockedRecheck.getAsLong();
                if (now < last) throw new IllegalArgumentException("INVALID_SERVER_CLOCK");
                try (var s = c.prepareStatement("SELECT approval_id FROM " + receipts +
                        " WHERE approval_id=? OR nonce=?")) {
                    s.setString(1,pending.approvalId().toString());
                    s.setString(2,envelope.nonce().toString());
                    try (var rs = s.executeQuery()) {
                        if (rs.next()) throw new IllegalArgumentException("REPLAY_OR_ALREADY_DECIDED");
                    }
                }
                if (count < 0 || count >= CAPACITY)
                    throw new IllegalArgumentException("REHEARSAL_CAPACITY");
                try (var s = c.prepareStatement("INSERT INTO " + receipts +
                        " (approval_id,nonce,decision,proof_digest,recorded_at) VALUES (?,?,?,?,?)")) {
                    s.setString(1,pending.approvalId().toString());
                    s.setString(2,envelope.nonce().toString());
                    s.setString(3,envelope.decision().name());
                    s.setString(4,hash(signedBytes(pending,envelope)));
                    s.setLong(5,now);
                    if (s.executeUpdate()!=1) throw new SQLException("RECEIPT_INSERT_FAILED");
                }
                try (var s = c.prepareStatement("UPDATE " + state + " SET last_time=?,total=? WHERE id=1")) {
                    s.setLong(1,now);
                    s.setInt(2,count+1);
                    if (s.executeUpdate()!=1) throw new SQLException("JOURNAL_UPDATE_FAILED");
                }
                c.commit();
            } catch (SQLException | RuntimeException e) {
                c.rollback();
                throw e;
            }
        } catch (SQLException e) {
            throw new IllegalStateException("TEST_JOURNAL_UNAVAILABLE", e);
        }
    }

    // A separate connection holds the exact singleton lock for deterministic
    // contention regressions. Test must release it before joining submitter.
    Connection holdLockForTest() throws SQLException {
        Connection c = open();
        try {
            c.setAutoCommit(false);
            try (var s = c.prepareStatement("SELECT id FROM " + state + " WHERE id=1 FOR UPDATE");
                 var rs = s.executeQuery()) {
                if (!rs.next()) throw new SQLException("MISSING_TEST_JOURNAL");
            }
            return c;
        } catch (SQLException | RuntimeException e) {
            c.close();
            throw e;
        }
    }

    int count() throws SQLException {
        try (var c = open(); var s = c.createStatement();
             var rs = s.executeQuery("SELECT COUNT(*) FROM " + receipts)) {
            if (!rs.next()) throw new SQLException("MISSING_COUNT");
            return rs.getInt(1);
        }
    }

    // Test-only fault injection: fail the metadata update after receipt insertion.
    void breakMetadataUpdate() throws SQLException {
        try (var c = open(); var s = c.createStatement()) {
            s.execute("ALTER TABLE " + state + " ADD CONSTRAINT CHECK (total=0)");
        }
    }

    private static String hash(byte[] bytes) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); }
        catch (NoSuchAlgorithmException e) { throw new IllegalStateException(e); }
    }
}
