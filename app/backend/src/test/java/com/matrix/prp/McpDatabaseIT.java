package com.matrix.prp;

import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.finance.model.CreateFinanceTransactionRequest;
import com.matrix.prp.mcp.McpDraftService;
import com.matrix.prp.tasks.model.CreateTaskRequest;
import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.web.server.ResponseStatusException;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * True MySQL integration: JDBC draft locks and MyBatis business inserts must
 * participate in the same Spring transaction and preserve tenant isolation.
 * CI provisions a disposable MySQL database with all migrations through V27 (MCP drafts from V25).
 */
@SpringBootTest
@ActiveProfiles("video-integration")
@TestPropertySource(properties = {
    "matrix-prp.mcp.enabled=true",
    "matrix-prp.mcp.write-enabled=true",
    "spring.ai.mcp.server.enabled=true"
})
class McpDatabaseIT {
    @Autowired McpDraftService drafts;
    @Autowired UserStore users;
    @Autowired PasswordEncoder encoder;
    @Autowired JdbcTemplate jdbc;
    @Autowired com.matrix.prp.tasks.service.TaskService tasks;
    @Autowired org.springframework.transaction.PlatformTransactionManager transactions;

    @Test
    void approvedTaskUpdateAndDeleteAreOwnerScopedAndIdempotent() {
        String password = "synthetic-mcp-crud-2026";
        var owner = createUser(password);
        var stranger = createUser("another-synthetic-password");
        as(owner);
        var original = tasks.create(new CreateTaskRequest("work", "Before", "", "low", java.time.LocalDate.now().plusDays(2)));
        var replacement = new CreateTaskRequest("work", "After", "Reviewed", "high", null);
        var update = drafts.prepareTaskChange(original.id(), replacement, "done", false);
        assertThat(tasks.get(original.id()).title()).isEqualTo("Before");
        drafts.approve(update.draftId(), password);
        drafts.confirm(update.draftId());
        assertThat(tasks.get(original.id()).title()).isEqualTo("After");
        assertThat(tasks.get(original.id()).status()).isEqualTo("done");
        assertThat(tasks.get(original.id()).dueDate()).isNull();
        assertThat(drafts.confirm(update.draftId()).alreadySaved()).isTrue();
        as(stranger);
        assertThatThrownBy(() -> drafts.prepareTaskChange(original.id(), null, null, true))
            .isInstanceOf(ResponseStatusException.class);
        as(owner);
        var deletion = drafts.prepareTaskChange(original.id(), null, null, true);
        drafts.approve(deletion.draftId(), password);
        assertThat(drafts.confirm(deletion.draftId()).saved().path("deleted").asBoolean()).isTrue();
        assertThat(drafts.confirm(deletion.draftId()).alreadySaved()).isTrue();
        assertThat(jdbc.queryForObject("SELECT deleted FROM prp_tasks WHERE id=? AND user_id=?", Integer.class,
            original.id(), owner.id())).isEqualTo(1);
    }

    @Test
    void changedTaskCannotBeDeletedByAnOlderApproval() {
        String password = "synthetic-mcp-conflict-2026";
        var owner = createUser(password);
        as(owner);
        var task = tasks.create(new CreateTaskRequest("work", "Before", "", "low", null));
        var deletion = drafts.prepareTaskChange(task.id(), null, null, true);
        drafts.approve(deletion.draftId(), password);
        tasks.update(task.id(), new CreateTaskRequest("work", "Newer human edit", "", "low", null));
        assertThatThrownBy(() -> drafts.confirm(deletion.draftId())).isInstanceOf(ResponseStatusException.class)
            .satisfies(e -> assertThat(((ResponseStatusException)e).getStatusCode()).isEqualTo(HttpStatus.CONFLICT));
        assertThat(tasks.get(task.id()).title()).isEqualTo("Newer human edit");
        assertThat(drafts.review(deletion.draftId()).status()).isEqualTo("APPROVED");
    }

    @Test
    void taskMutationAndDraftConsumptionRollbackTogether() {
        String password = "synthetic-mcp-rollback-2026";
        var owner = createUser(password);
        as(owner);
        var task = tasks.create(new CreateTaskRequest("work", "Before", "", "low", null));
        var deletion = drafts.prepareTaskChange(task.id(), null, null, true);
        drafts.approve(deletion.draftId(), password);
        var transaction = new org.springframework.transaction.support.TransactionTemplate(transactions);
        assertThatThrownBy(() -> transaction.executeWithoutResult(status -> {
            drafts.confirm(deletion.draftId());
            throw new IllegalStateException("SYNTHETIC_TRANSACTION_FAILURE");
        })).isInstanceOf(IllegalStateException.class);
        assertThat(tasks.get(task.id()).title()).isEqualTo("Before");
        assertThat(drafts.review(deletion.draftId()).status()).isEqualTo("APPROVED");
        assertThat(drafts.confirm(deletion.draftId()).alreadySaved()).isFalse();
    }

    @org.springframework.beans.factory.annotation.Value("${spring.datasource.url}") String databaseUrl;
    @org.springframework.beans.factory.annotation.Value("${spring.datasource.username}") String databaseUser;
    @org.springframework.beans.factory.annotation.Value("${spring.datasource.password}") String databasePassword;

    @Test
    void draftTtlUsesDatabaseEpochEvenWithMismatchedJdbcZoneAndCapsLegacyRows() throws Exception {
        var owner = createUser("synthetic-mcp-clock-password");
        as(owner);
        // A separate disposable connection reproduces staging: server UTC, JDBC Shanghai.
        // Do not alter the global JVM zone or the shared Spring datasource.
        String url = databaseUrl.replaceAll("(?i)([?&])(serverTimezone|connectionTimeZone|forceConnectionTimeZoneToSession|preserveInstants)=[^&]*", "$1")
            .replace("?&", "?").replaceAll("&+", "&");
        if (!url.contains("?")) url += "?";
        if (!url.endsWith("?") && !url.endsWith("&")) url += "&";
        url += "connectionTimeZone=Asia%2FShanghai&preserveInstants=true&forceConnectionTimeZoneToSession=false";
        try (var connection = java.sql.DriverManager.getConnection(url, databaseUser, databasePassword)) {
            try (var stmt = connection.createStatement()) { stmt.execute("SET SESSION time_zone='+00:00'"); }
            connection.setAutoCommit(false);
            try {
                var mixedDb = new JdbcTemplate(new org.springframework.jdbc.datasource.SingleConnectionDataSource(connection, true));
                var taskSink = org.mockito.Mockito.mock(com.matrix.prp.tasks.service.TaskService.class);
                var mixed = new McpDraftService(mixedDb, new com.fasterxml.jackson.databind.ObjectMapper().findAndRegisterModules(),
                    jakarta.validation.Validation.buildDefaultValidatorFactory().getValidator(), taskSink,
                    org.mockito.Mockito.mock(com.matrix.prp.finance.service.FinanceService.class),
                    org.mockito.Mockito.mock(com.matrix.prp.records.service.RecordService.class),
                    users, encoder, true, "");
                var request = new CreateTaskRequest("work", "Synthetic clock regression", null, "low", null);
                var draft = mixed.prepare(McpDraftService.Kind.TASK, request);
                long ttl = mixedDb.queryForObject("SELECT UNIX_TIMESTAMP(expires_at)-UNIX_TIMESTAMP(created_at) " +
                    "FROM prp_mcp_write_drafts WHERE id=? AND user_id=?", Long.class, draft.draftId(), owner.id());
                assertThat(ttl).isEqualTo(900L);
                long epoch = mixedDb.queryForObject("SELECT UNIX_TIMESTAMP(expires_at) FROM prp_mcp_write_drafts WHERE id=?",
                    Long.class, draft.draftId());
                assertThat(java.time.Instant.parse(draft.expiresAt()).getEpochSecond()).isEqualTo(epoch);
                assertThat(mixed.review(draft.draftId()).expiresAt()).isEqualTo(draft.expiresAt());

                // Reproduce the old Timestamp binding in the deliberately mismatched connection.
                mixedDb.update("UPDATE prp_mcp_write_drafts SET expires_at=? WHERE id=?",
                    java.sql.Timestamp.from(java.time.Instant.now().plusSeconds(900)), draft.draftId());
                assertThat(mixedDb.queryForObject("SELECT UNIX_TIMESTAMP(expires_at)-UNIX_TIMESTAMP(created_at) " +
                    "FROM prp_mcp_write_drafts WHERE id=?", Long.class, draft.draftId())).isBetween(29690L, 29730L);
                // Exact boundary: created + 900s is already due, despite the stored future expiry.
                mixedDb.update("UPDATE prp_mcp_write_drafts SET created_at=DATE_SUB(CURRENT_TIMESTAMP,INTERVAL 15 MINUTE) WHERE id=?",
                    draft.draftId());
                long capped = mixedDb.queryForObject("SELECT UNIX_TIMESTAMP(created_at)+900 FROM prp_mcp_write_drafts WHERE id=?",
                    Long.class, draft.draftId());
                assertThat(java.time.Instant.parse(mixed.review(draft.draftId()).expiresAt()).getEpochSecond()).isEqualTo(capped);
                assertThatThrownBy(() -> mixed.approve(draft.draftId(), "synthetic-mcp-clock-password"))
                    .isInstanceOfSatisfying(ResponseStatusException.class,
                        e -> assertThat(e.getStatusCode()).isEqualTo(HttpStatus.CONFLICT));
                assertThat(mixed.review(draft.draftId()).status()).isEqualTo("PENDING");
                for (int i=0; i<49; i++) {
                    mixedDb.update("INSERT INTO prp_mcp_write_drafts (id,user_id,kind,payload_json,created_at,expires_at) " +
                        "SELECT ?,user_id,kind,payload_json,created_at,expires_at FROM prp_mcp_write_drafts WHERE id=?",
                        UUID.randomUUID().toString(), draft.draftId());
                }
                // The 50 expired legacy PENDING rows must not consume the live draft quota.
                var fresh = mixed.prepare(McpDraftService.Kind.TASK, request);
                assertThat(mixed.approve(fresh.draftId(), "synthetic-mcp-clock-password").status()).isEqualTo("APPROVED");
                mixedDb.update("UPDATE prp_mcp_write_drafts SET created_at=DATE_SUB(CURRENT_TIMESTAMP,INTERVAL 16 MINUTE), " +
                    "expires_at=DATE_ADD(CURRENT_TIMESTAMP,INTERVAL 8 HOUR) WHERE id=?", fresh.draftId());
                assertThatThrownBy(() -> mixed.confirm(fresh.draftId())).isInstanceOfSatisfying(ResponseStatusException.class,
                    e -> assertThat(e.getStatusCode()).isEqualTo(HttpStatus.CONFLICT));
                assertThat(mixed.review(fresh.draftId()).status()).isEqualTo("APPROVED");
                org.mockito.Mockito.verifyNoInteractions(taskSink);
                System.out.println("CI_MCP_DRAFT_TTL_MIXED_ZONE=PASS");
            } finally { connection.rollback(); }
        }
    }

    @AfterEach
    void cleanupIdentity() { SecurityContextHolder.clearContext(); }

    private UserAccount createUser(String password) {
        String name = "mcp_ci_" + UUID.randomUUID().toString().replace("-", "").substring(0, 18);
        return users.create(name, "MCP CI user", encoder.encode(password), false);
    }

    private void as(UserAccount user) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(user.profile(), null, List.of()));
    }

    @Test
    void financeWriteCannotCrossAccountsAndConfirmationIsIdempotent() {
        String password = "mcp-it-password-2026";
        UserAccount owner = createUser(password), stranger = createUser("other-" + password);
        String unique = "mcp-it-" + UUID.randomUUID();
        as(owner);
        var draft = drafts.prepare(McpDraftService.Kind.FINANCE,
            new CreateFinanceTransactionRequest("expense", new BigDecimal("31.65"),
                "餐饮", "mcp-ci-wallet-" + owner.id(), unique, "idempotent integration test", null));
        assertThat(drafts.review(draft.draftId()).status()).isEqualTo("PENDING");
        assertThatThrownBy(() -> drafts.confirm(draft.draftId()))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e -> assertThat(((ResponseStatusException) e).getStatusCode())
                .isEqualTo(HttpStatus.CONFLICT));

        as(stranger);
        assertThatThrownBy(() -> drafts.review(draft.draftId()))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e -> assertThat(((ResponseStatusException) e).getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND));
        assertThatThrownBy(() -> drafts.approve(draft.draftId(), password))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e -> assertThat(((ResponseStatusException) e).getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND));
        assertThatThrownBy(() -> drafts.confirm(draft.draftId()))
            .isInstanceOf(ResponseStatusException.class);

        as(owner);
        assertThat(drafts.approve(draft.draftId(), password).status()).isEqualTo("APPROVED");
        var first = drafts.confirm(draft.draftId());
        var replay = drafts.confirm(draft.draftId());
        assertThat(first.alreadySaved()).isFalse();
        assertThat(replay.alreadySaved()).isTrue();
        assertThat(replay.saved().toString()).isEqualTo(first.saved().toString());
        assertThat(first.saved().path("id").asLong()).isPositive();
        assertThat(jdbc.queryForObject(
            "SELECT COUNT(*) FROM prp_finance_transactions WHERE user_id=? AND merchant=?",
            Integer.class, owner.id(), unique)).isEqualTo(1);
        assertThat(jdbc.queryForObject(
            "SELECT COUNT(*) FROM prp_finance_transactions WHERE user_id=? AND merchant=?",
            Integer.class, stranger.id(), unique)).isZero();
        assertThat(drafts.review(draft.draftId()).status()).isEqualTo("CONSUMED");
    }

    @Test
    void simultaneousConfirmationsCreateOneTask() throws Exception {
        String password = "mcp-concurrent-2026";
        UserAccount owner = createUser(password);
        String title = "mcp-concurrent-" + UUID.randomUUID();
        as(owner);
        var draft = drafts.prepare(McpDraftService.Kind.TASK,
            new CreateTaskRequest("work", title, "Concurrency test", "high", null));
        assertThat(drafts.approve(draft.draftId(), password).status()).isEqualTo("APPROVED");

        var start = new CountDownLatch(1);
        try (var pool = Executors.newFixedThreadPool(2)) {
            var action = (java.util.concurrent.Callable<McpDraftService.Result>) () -> {
                as(owner);  // Authentication is per request/thread, never borrowed from the model.
                try {
                    if (!start.await(5, TimeUnit.SECONDS))
                        throw new IllegalStateException("Concurrent test start timeout");
                    return drafts.confirm(draft.draftId());
                } finally {
                    SecurityContextHolder.clearContext();
                }
            };
            var first = pool.submit(action);
            var second = pool.submit(action);
            start.countDown();
            var one = first.get(20, TimeUnit.SECONDS);
            var two = second.get(20, TimeUnit.SECONDS);
            assertThat(one.saved().toString()).isEqualTo(two.saved().toString());
            assertThat(one.alreadySaved() != two.alreadySaved()).isTrue();
        }
        assertThat(jdbc.queryForObject(
            "SELECT COUNT(*) FROM prp_tasks WHERE user_id=? AND title=?",
            Integer.class, owner.id(), title)).isEqualTo(1);
    }

    @Test
    void rejectedDraftCannotWriteAndFailedPasswordsPersist() {
        String password = "mcp-invalid-test-2026";
        UserAccount owner = createUser(password);
        as(owner);
        var draft = drafts.prepare(McpDraftService.Kind.TASK,
            new CreateTaskRequest("life", "reject-" + UUID.randomUUID(), null, "low", null));
        for (int i=1; i<=5; i++) {
            var outcome = drafts.approve(draft.draftId(), "wrong password");
            assertThat(outcome.remainingAttempts()).isEqualTo(5-i);
        }
        assertThat(drafts.review(draft.draftId()).status()).isEqualTo("REJECTED");
        assertThatThrownBy(() -> drafts.confirm(draft.draftId()))
            .isInstanceOf(ResponseStatusException.class);
        assertThat(jdbc.queryForObject(
            "SELECT approval_failures FROM prp_mcp_write_drafts WHERE id=?",
            Integer.class, draft.draftId())).isEqualTo(5);
    }
}
