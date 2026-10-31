package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.tasks.model.CreateTaskRequest;
import com.matrix.prp.tasks.model.TaskFilter;
import com.matrix.prp.tasks.service.TaskService;
import java.util.List;
import java.util.UUID;
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

/**
 * Disposable real-MySQL test of the EXISTING producer task repository.
 * No producer HTTP endpoint, no Keycloak, no production database,
 * no arbitrary caller-supplied owner ID, no OAuth or writes via MCP.
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
class TaskReadProducerDatabaseIT {
    @Autowired TaskService tasks;
    @Autowired UserStore users;
    @Autowired PasswordEncoder passwords;
    @Autowired JdbcTemplate jdbc;

    private UserAccount createSyntheticOwner() {
        String username = "ci_task_prod_" + UUID.randomUUID().toString().replace("-", "").substring(0, 14);
        return users.create(username, "Synthetic task owner", passwords.encode("synthetic-ci-only"), false);
    }

    private void as(UserAccount owner) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(owner.profile(), null, List.of()));
    }

    @AfterEach
    void clearPrincipal() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void mysqlSeparatesOwnersEvenWithMoreThanTwentyTasksAndStatusFilter() {
        UserAccount a = createSyntheticOwner();
        UserAccount b = createSyntheticOwner();
        as(a);
        for (int i = 0; i < 24; i++) {
            tasks.create(new CreateTaskRequest("work", "CI-A-" + i,
                "synthetic only", "low", null));
        }
        var aDone = tasks.create(new CreateTaskRequest("work", "CI-A-done",
            "synthetic only", "medium", null));
        tasks.updateStatus(aDone.id(), "done");

        as(b);
        for (int i = 0; i < 3; i++) {
            tasks.create(new CreateTaskRequest("work", "CI-B-" + i,
                "synthetic only", "low", null));
        }

        // MyBatis must apply both owner predicate and LIMIT IN MYSQL, not
        // merely filter the result in the MCP caller.
        as(a);
        var first20 = tasks.listLimited(new TaskFilter(null, null, null, null), 20);
        assertThat(first20).hasSize(20);
        assertThat(first20).allSatisfy(t -> assertThat(t.title()).startsWith("CI-A-"));
        var done = tasks.listLimited(new TaskFilter("done", null, null, null), 20);
        assertThat(done).hasSize(1).extracting("id").containsExactly(aDone.id());

        as(b);
        var other = tasks.listLimited(new TaskFilter(null, null, null, null), 20);
        assertThat(other).hasSize(3);
        assertThat(other).allSatisfy(t -> assertThat(t.title()).startsWith("CI-B-"));
        assertThat(tasks.listLimited(new TaskFilter("done", null, null, null), 20)).isEmpty();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM prp_tasks WHERE user_id=? AND deleted=0",
            Integer.class, a.id())).isEqualTo(25);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM prp_tasks WHERE user_id=? AND deleted=0",
            Integer.class, b.id())).isEqualTo(3);
    }

    @Test
    void mysqlCannotGetAnotherOwnersTaskAndAnonymousCannotRead() {
        UserAccount a = createSyntheticOwner();
        UserAccount b = createSyntheticOwner();
        as(a);
        var secret = tasks.create(new CreateTaskRequest("work",
            "CI-owner-A-only-" + UUID.randomUUID(), "synthetic", "high", null));

        as(b);
        assertThatThrownBy(() -> tasks.get(secret.id()))
            .isInstanceOf(com.matrix.prp.common.api.ResourceNotFoundException.class);
        assertThat(tasks.listLimited(new TaskFilter(null, null, null, null), 20))
            .noneSatisfy(task -> assertThat(task.id()).isEqualTo(secret.id()));

        SecurityContextHolder.clearContext();
        assertThatThrownBy(() -> tasks.listLimited(new TaskFilter(null, null, null, null), 20))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(ex -> assertThat(((ResponseStatusException) ex).getStatusCode())
                .isEqualTo(HttpStatus.UNAUTHORIZED));
    }
}
