package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;

import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.tasks.model.CreateTaskRequest;
import com.matrix.prp.tasks.model.TaskFilter;
import com.matrix.prp.tasks.service.TaskService;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

/**
 * CI-ONLY, throwaway MySQL concurrency and authorization-epoch proof.
 * These tables and methods are test fixtures, NOT a production producer
 * endpoint, DB migration, active consent workflow or OAuth authenticator.
 * Every mutation is limited to the exact disposable CI schema; otherwise
 * the fixture fails BEFORE a DDL statement can execute.
 */
@SpringBootTest
@ActiveProfiles("video-integration")
@TestPropertySource(properties = {
    "matrix-prp.mcp.enabled=false",
    "matrix-prp.mcp.oauth.enabled=false",
    "matrix-prp.mcp.write-enabled=false",
    "spring.ai.mcp.server.enabled=false",
    "matrix-prp.ai.spring-ai.enabled=false",
    "matrix-prp.ai.spring-ai.tools-enabled=false"
})
class ProducerTaskDelegationMysqlProofIT {
    private static final String CONSENT_TABLE = "ci_producer_owner_consent_proof";
    private static final String REPLAY_TABLE = "ci_producer_jti_replay_proof";
    private static final String ISSUER = "https://ci-issuer.invalid/realms/synthetic";
    private static final String CLIENT = "https://chatgpt.com/oauth/client.json";
    @Autowired JdbcTemplate jdbc;
    @Autowired PlatformTransactionManager transactionManager;
    @Autowired UserStore users;
    @Autowired PasswordEncoder passwords;
    @Autowired TaskService tasks;

    private void assertDisposableCiOnly() {
        String jdbcUrl = System.getenv("MATRIX_PRP_DB_URL");
        if (!"true".equals(System.getenv("GITHUB_ACTIONS"))
                || !"YES".equals(System.getenv("PRP_CI_DISPOSABLE_DB_ONLY"))
                || jdbcUrl == null
                || !jdbcUrl.startsWith("jdbc:mysql://127.0.0.1:13307/"
                    + "matrix_prp_task_producer_ci?")
                || !"matrix_prp_task_producer_ci".equals(
                    jdbc.queryForObject("SELECT DATABASE()", String.class))) {
            throw new SecurityException("DISPOSABLE_PRODUCER_MYSQL_ONLY");
        }
    }

    @BeforeEach
    void createCiOnlyTables() {
        assertDisposableCiOnly();
        jdbc.execute("CREATE TABLE " + CONSENT_TABLE + " ("
            + "issuer VARCHAR(255) NOT NULL, subject VARCHAR(255) NOT NULL,"
            + "client_id VARCHAR(255) NOT NULL, owner_id BIGINT NOT NULL,"
            + "consent_epoch BIGINT NOT NULL, status VARCHAR(16) NOT NULL,"
            + "PRIMARY KEY(issuer,subject,client_id)) ENGINE=InnoDB");
        jdbc.execute("CREATE TABLE " + REPLAY_TABLE + " ("
            + "token_digest CHAR(64) NOT NULL PRIMARY KEY,"
            + "expires_at DATETIME(6) NOT NULL) ENGINE=InnoDB");
    }

    @AfterEach
    void clearCiOnlyTables() {
        assertDisposableCiOnly();
        jdbc.execute("DROP TABLE IF EXISTS " + REPLAY_TABLE);
        jdbc.execute("DROP TABLE IF EXISTS " + CONSENT_TABLE);
    }

    private long verifiedOwner(String subject, long epoch) {
        // ASSUMES separate external JWT signature + TLS peer verification.
        // A caller-provided owner ID is NEVER an input to this lookup.
        List<Long> matches = jdbc.query(
            "SELECT owner_id FROM " + CONSENT_TABLE + " WHERE issuer=? "
            + "AND subject=? AND client_id=? AND consent_epoch=? AND status='ACTIVE'",
            (rs, row) -> rs.getLong(1), ISSUER, subject, CLIENT, epoch);
        return matches.isEmpty() ? -1 : matches.getFirst();
    }

    private long verifiedOwnerForShare(String subject, long epoch) {
        // Must run WITHIN the same SQL transaction that performs a read.
        // A separate autocommit lookup followed by task SQL is TOCTOU-unsafe.
        List<Long> rows = jdbc.query(
            "SELECT owner_id FROM " + CONSENT_TABLE + " WHERE issuer=? "
            + "AND subject=? AND client_id=? AND consent_epoch=? "
            + "AND status='ACTIVE' FOR SHARE",
            (rs, row) -> rs.getLong(1), ISSUER, subject, CLIENT, epoch);
        return rows.isEmpty() ? -1 : rows.getFirst();
    }

    @Test
    void inFlightOwnerReadCommitsBeforeConcurrentRevocationCanComplete() throws Exception {
        String subject = "ci-race-" + UUID.randomUUID();
        String username = "ci_race_" + UUID.randomUUID().toString().replace("-", "").substring(0, 15);
        UserAccount owner = users.create(username, "Synthetic read/revoke owner",
            passwords.encode("ci-only-ephemeral"), false);
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(owner.profile(), null, List.of()));
        try {
            tasks.create(new CreateTaskRequest("work", "CI-race-owned-task",
                "synthetic only", "low", null));
        } finally {
            SecurityContextHolder.clearContext();
        }
        jdbc.update("INSERT INTO " + CONSENT_TABLE
            + "(issuer,subject,client_id,owner_id,consent_epoch,status) "
            + "VALUES (?,?,?,?,?,'ACTIVE')", ISSUER, subject, CLIENT, owner.id(), 22L);

        CountDownLatch readLocked = new CountDownLatch(1);
        CountDownLatch releaseRead = new CountDownLatch(1);
        CountDownLatch revokerStarted = new CountDownLatch(1);
        var executor = Executors.newFixedThreadPool(2);
        try {
            // The row lock stays held for the entire producer-side task
            // query AND until the read's DB transaction actually commits.
            var read = executor.submit(() ->
                new TransactionTemplate(transactionManager).execute(tx -> {
                    assertThat(verifiedOwnerForShare(subject, 22)).isEqualTo(owner.id());
                    readLocked.countDown();
                    try {
                        if (!releaseRead.await(12, TimeUnit.SECONDS))
                            throw new IllegalStateException("CI_READ_RELEASE_TIMEOUT");
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException("CI_READ_INTERRUPTED", e);
                    }
                    SecurityContextHolder.getContext().setAuthentication(
                        new UsernamePasswordAuthenticationToken(
                            owner.profile(), null, List.of()));
                    try {
                        return tasks.listLimited(new TaskFilter(null, null, null, null), 20)
                            .stream().filter(t -> t.title().equals("CI-race-owned-task")).count();
                    } finally {
                        SecurityContextHolder.clearContext();
                    }
                })
            );
            assertThat(readLocked.await(10, TimeUnit.SECONDS)).isTrue();
            var revoke = executor.submit(() -> {
                revokerStarted.countDown();
                return jdbc.update("UPDATE " + CONSENT_TABLE
                    + " SET status='REVOKED',consent_epoch=consent_epoch+1"
                    + " WHERE issuer=? AND subject=? AND client_id=?",
                    ISSUER, subject, CLIENT);
            });
            assertThat(revokerStarted.await(10, TimeUnit.SECONDS)).isTrue();
            // UPDATE must not COMMIT while a previously authorized SQL read
            // holds a shared lock. This is a short deterministic window,
            // NOT proof of service-level revocation latency guarantees.
            Thread.sleep(300);
            assertThat(revoke.isDone()).isFalse();
            releaseRead.countDown();
            assertThat(read.get(15, TimeUnit.SECONDS)).isEqualTo(1L);
            assertThat(revoke.get(15, TimeUnit.SECONDS)).isEqualTo(1);
            assertThat(verifiedOwner(subject, 22)).isEqualTo(-1L);
            assertThat(verifiedOwner(subject, 23)).isEqualTo(-1L);
        } finally {
            releaseRead.countDown();
            executor.shutdownNow();
            SecurityContextHolder.clearContext();
        }
    }

    @Test
    void parallelClientsCompeteForOneDatabaseJtiOnlyOneWins() throws Exception {
        // The JTI surrogate is generated only in CI, stored by digest in
        // the fixture to avoid persisting signed JWTs or their plaintext IDs.
        String digest = UUID.randomUUID().toString().replace("-", "")
            + UUID.randomUUID().toString().replace("-", "");
        int peers = 12;
        CountDownLatch start = new CountDownLatch(1);
        var executor = Executors.newFixedThreadPool(peers);
        try {
            List<Callable<Integer>> attempts = new ArrayList<>();
            for (int i = 0; i < peers; i++) {
                attempts.add(() -> {
                    if (!start.await(12, TimeUnit.SECONDS))
                        throw new IllegalStateException("CI_CONCURRENT_START_TIMEOUT");
                    return jdbc.update(
                        "INSERT IGNORE INTO " + REPLAY_TABLE
                        + "(token_digest,expires_at) "
                        + "VALUES (?,DATE_ADD(NOW(6),INTERVAL 2 MINUTE))", digest);
                });
            }
            var submitted = new ArrayList<java.util.concurrent.Future<Integer>>();
            for (var attempt : attempts) submitted.add(executor.submit(attempt));
            start.countDown();
            int accepted = 0;
            for (var future : submitted)
                accepted += future.get(20, TimeUnit.SECONDS);
            assertThat(accepted).isEqualTo(1);
            assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM " + REPLAY_TABLE
                + " WHERE token_digest=?", Integer.class, digest)).isEqualTo(1);
            assertThat(jdbc.update("INSERT IGNORE INTO " + REPLAY_TABLE
                + "(token_digest,expires_at) VALUES (?,DATE_ADD(NOW(6),INTERVAL 2 MINUTE))",
                digest)).isZero();
        } finally {
            executor.shutdownNow();
        }
    }

    @Test
    void revokedThenRegrantedConsentNeverRevivesPreviouslyIssuedEpoch() {
        String alice = "ci-alice-" + UUID.randomUUID();
        String bob = "ci-bob-" + UUID.randomUUID();
        jdbc.update("INSERT INTO " + CONSENT_TABLE
            + "(issuer,subject,client_id,owner_id,consent_epoch,status) "
            + "VALUES (?,?,?,?,?,'ACTIVE')", ISSUER, alice, CLIENT, 12001L, 7);
        jdbc.update("INSERT INTO " + CONSENT_TABLE
            + "(issuer,subject,client_id,owner_id,consent_epoch,status) "
            + "VALUES (?,?,?,?,?,'ACTIVE')", ISSUER, bob, CLIENT, 12002L, 3);
        assertThat(verifiedOwner(alice, 7)).isEqualTo(12001L);
        assertThat(verifiedOwner(bob, 3)).isEqualTo(12002L);
        assertThat(verifiedOwner(alice, 3)).isEqualTo(-1);

        // Revocation changes epoch in an authoritative producer table.
        jdbc.update("UPDATE " + CONSENT_TABLE
            + " SET status='REVOKED',consent_epoch=consent_epoch+1 "
            + "WHERE issuer=? AND subject=? AND client_id=?", ISSUER, alice, CLIENT);
        assertThat(verifiedOwner(alice, 7)).isEqualTo(-1);
        assertThat(verifiedOwner(alice, 8)).isEqualTo(-1);
        // A NEW explicit authorization bumps epoch again; an old token
        // issued under epoch 7 must remain invalid even after regrant.
        jdbc.update("UPDATE " + CONSENT_TABLE
            + " SET status='ACTIVE',consent_epoch=consent_epoch+1 "
            + "WHERE issuer=? AND subject=? AND client_id=?", ISSUER, alice, CLIENT);
        assertThat(verifiedOwner(alice, 7)).isEqualTo(-1);
        assertThat(verifiedOwner(alice, 9)).isEqualTo(12001L);
        assertThat(verifiedOwner(bob, 3)).isEqualTo(12002L);
        assertThat(verifiedOwner("unknown", 7)).isEqualTo(-1);
    }
}
