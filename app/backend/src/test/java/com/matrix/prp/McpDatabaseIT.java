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
