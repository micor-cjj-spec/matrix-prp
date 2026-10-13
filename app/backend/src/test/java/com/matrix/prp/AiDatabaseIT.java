package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import com.matrix.prp.ai.AiStore;
import com.matrix.prp.ai.JdbcAiStore;
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
}
