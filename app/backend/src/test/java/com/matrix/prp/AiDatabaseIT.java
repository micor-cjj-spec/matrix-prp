package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import com.matrix.prp.ai.AiStore;
import com.matrix.prp.ai.JdbcAiStore;
import com.matrix.prp.ai.AiToolRegistry;
import com.matrix.prp.ai.AiNavigationResolver;
import com.matrix.prp.auth.model.UserProfile;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.web.server.ResponseStatusException;

@SpringBootTest
@ActiveProfiles("video-integration")
class AiDatabaseIT {
    @Autowired AiStore store;
    @Autowired JdbcTemplate jdbc;
    @Autowired ObjectMapper mapper;
    @Autowired AiToolRegistry tools;
    @Autowired AiNavigationResolver navigation;

    @Test
    void conversationsArePrivateAndQuotaReservationsAreTransactional() {
        long first = 908881L, second = 908882L;
        String month = "2098-11";
        String id = store.create(first, "AI database integration " + UUID.randomUUID()).id();
        store.append(first, id, "user", "Confidential");
        assertThat(store.owns(first, id)).isTrue();
        assertThat(store.owns(second, id)).isFalse();
        assertThat(store.messages(second, id)).isEmpty();
        assertThat(store.list(second)).noneMatch(c -> c.id().equals(id));
        assertThatThrownBy(() -> store.append(second, id, "assistant", "Unauthorized"))
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(ex -> assertThat(((ResponseStatusException) ex).getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND));
        assertThat(store.messages(first, id)).hasSize(1);

        // The second failed reservation must not leak an increment to the global ledger.
        String uniqueMonth = "20" + (10 + (int)(System.nanoTime() % 75)) + "-12";
        store.reserve(first, uniqueMonth, 300, 1, 400, 5, 5000);
        assertThatThrownBy(() -> store.reserve(first, uniqueMonth, 300, 1, 400, 5, 5000))
                .isInstanceOf(ResponseStatusException.class);
        assertThat(store.usage(first, uniqueMonth).requests()).isEqualTo(1);
        store.completed(first, uniqueMonth, 99, 12);
        assertThat(store.usage(first, uniqueMonth).inputTokens()).isEqualTo(99);
    }

    @Test
    void paginatesMoreThanTwoHundredMessagesWithoutLosingNewestOrTenantIsolation() {
        long owner = 908883L, other = 908884L;
        String id = store.create(owner, "Pagination " + UUID.randomUUID()).id();
        for (int i = 0; i < 205; i++) store.append(owner, id, "user", "message-" + i);

        var latest = store.messages(owner, id);
        assertThat(latest).hasSize(200);
        assertThat(latest.getFirst().content()).isEqualTo("message-5");
        assertThat(latest.getLast().content()).isEqualTo("message-204");

        var older = store.messages(owner, id, latest.getFirst().id(), 201);
        assertThat(older).hasSize(5);
        assertThat(older.getFirst().content()).isEqualTo("message-0");
        assertThat(older.getLast().content()).isEqualTo("message-4");
        assertThat(store.messages(owner, id, older.getFirst().id(), 201)).isEmpty();
        assertThat(store.messages(other, id, null, 201)).isEmpty();
    }

    @Test
    void savedConversationIsReopenedFromDatabaseAfterNewStoreInstance() {
        long owner = 908886L, other = 908887L;
        String id = store.create(owner, "Restore " + UUID.randomUUID()).id();
        store.append(owner, id, "user", "Question persisted");
        store.append(owner, id, "assistant", "Answer persisted");

        // Simulates a new page request / new JDBC store, not an in-memory chat.
        AiStore reloaded = new JdbcAiStore(jdbc);
        assertThat(reloaded.list(owner)).anyMatch(c -> c.id().equals(id));
        assertThat(reloaded.messages(owner, id)).extracting(AiStore.Message::content)
                .containsExactly("Question persisted", "Answer persisted");
        assertThat(reloaded.list(other)).noneMatch(c -> c.id().equals(id));
        assertThat(reloaded.messages(other, id)).isEmpty();
    }

    @Test
    void readonlyToolSqlLimitsAndCrossTenantIsolationAreEnforcedOnMySql() throws Exception {
        final long owner = 91818181L, stranger = 91818182L;
        final String month = "2026-10";
        try {
            for (int i=0; i<26; i++) {
                jdbc.update("""
                    INSERT INTO prp_tasks(user_id,module_code,title,description,priority,status,due_date,created_at,updated_at)
                    VALUES (?,'learning',?,'private body','medium','todo','2026-10-14',NOW(6),NOW(6))
                    """, owner, "tool-owner-task-"+i);
            }
            jdbc.update("""
                INSERT INTO prp_tasks(user_id,module_code,title,description,priority,status,due_date,created_at,updated_at)
                VALUES (?,'learning','tool-STRANGER-task','private','high','todo','2026-10-14',NOW(6),NOW(6))
                """, stranger);
            for(int i=0;i<15;i++) {
                jdbc.update("""
                    INSERT INTO prp_finance_transactions(user_id,type,amount,category,account,merchant,note,transaction_date,created_at,updated_at)
                    VALUES (?,'expense',1.00,'meal','cash','test','owner-private-note','2026-10-12',NOW(6),NOW(6))
                    """, owner);
            }
            jdbc.update("""
                INSERT INTO prp_finance_transactions(user_id,type,amount,category,account,merchant,note,transaction_date,created_at,updated_at)
                VALUES (?,'expense',999.00,'private','cash','test','STRANGER-finance-note','2026-10-12',NOW(6),NOW(6))
                """, stranger);
            var auth = new UsernamePasswordAuthenticationToken(
                new UserProfile(owner,"tools-owner","Tools Owner"),null,List.of());
            SecurityContextHolder.getContext().setAuthentication(auth);
            var taskResult=tools.execute("tasks_list",mapper.readTree("{}"),Set.of("tasks"));
            var taskItems=(List<?>)((Map<?,?>)taskResult.data()).get("items");
            assertThat(taskItems).hasSize(20);
            assertThat(mapper.writeValueAsString(taskItems)).doesNotContain("STRANGER","private body");
            assertThatThrownBy(()->tools.execute("finance_monthly",mapper.readTree("{}"),Set.of("tasks")))
                .isInstanceOf(ResponseStatusException.class);
            var financeResult=tools.execute("finance_monthly",
                mapper.readTree("{\"month\":\""+month+"\"}"),Set.of("finance"));
            var financeData=(Map<?,?>)financeResult.data();
            assertThat(financeData.get("expense")).isEqualTo("15.00");
            assertThat((List<?>)financeData.get("transactions")).hasSize(10);
            assertThat(mapper.writeValueAsString(financeData)).doesNotContain("STRANGER","999.00","owner-private-note");
            long strangerTask = jdbc.queryForObject(
                "SELECT id FROM prp_tasks WHERE user_id=? AND title='tool-STRANGER-task'",Long.class,stranger);
            assertThatThrownBy(()->navigation.resolve("tasks",
                mapper.createObjectNode().put("recordId",strangerTask)))
                .isInstanceOf(ResponseStatusException.class);
        } finally {
            SecurityContextHolder.clearContext();
            jdbc.update("DELETE FROM prp_finance_transactions WHERE user_id IN (?,?)",owner,stranger);
            jdbc.update("DELETE FROM prp_tasks WHERE user_id IN (?,?)",owner,stranger);
        }
    }

}
