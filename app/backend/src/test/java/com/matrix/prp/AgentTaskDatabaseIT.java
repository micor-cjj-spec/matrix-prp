package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import com.matrix.prp.ai.AgentTaskStore;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("video-integration")
class AgentTaskDatabaseIT {
    @Autowired AgentTaskStore store;
    @Test void approvalIsAtomicAndTasksStayPrivate() {
        long owner = 908951L, other = 908952L;
        AgentTaskStore.AgentTask t = store.create(owner,"PLAN","Database integration " + UUID.randomUUID());
        assertThat(store.find(other,t.id())).isEmpty();
        assertThat(store.list(other)).noneMatch(item -> item.id().equals(t.id()));
        assertThat(store.claim(other,t.id(),other)).isFalse();
        assertThat(store.claim(owner,t.id(),owner)).isTrue();
        assertThat(store.claim(owner,t.id(),owner)).isFalse();
        assertThat(store.cancel(owner,t.id())).isFalse();
        store.complete(other,t.id(),"Not allowed");
        assertThat(store.find(owner,t.id()).orElseThrow().result()).isNull();
        store.complete(owner,t.id(),"Safe written result");
        assertThat(store.find(owner,t.id()).orElseThrow().status()).isEqualTo("COMPLETED");
        assertThat(store.find(owner,t.id()).orElseThrow().result()).isEqualTo("Safe written result");
        assertThat(store.find(owner,t.id()).orElseThrow().approvedBy()).isEqualTo(owner);
        assertThat(store.find(owner,t.id()).orElseThrow().sessionRef()).contains(t.id());

        AgentTaskStore.AgentTask cancelled = store.create(owner,"ANALYZE","Cancel the draft");
        assertThat(store.cancel(owner,cancelled.id())).isTrue();
        assertThat(store.claim(owner,cancelled.id(),owner)).isFalse();
    }
}
