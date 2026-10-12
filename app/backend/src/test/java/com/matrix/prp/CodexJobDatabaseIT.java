package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import com.matrix.prp.ai.CodexJobStore;
import com.matrix.prp.ai.CodexWorkflowClient;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("video-integration")
class CodexJobDatabaseIT {
    @Autowired CodexJobStore store;
    @Test void approvalIsAtomicAndScopeIsolatedInRealMysql() {
        long owner=988715L,other=988716L;
        var job=store.create(owner,CodexWorkflowClient.REPOSITORY,"FIX","Fix a unit test "+UUID.randomUUID());
        assertThat(store.find(other,job.id())).isEmpty();
        assertThat(store.list(other())).noneMatch(x -> x.id().equals(job.id()));
        assertThat(store.claim(other,job.id(),other)).isFalse();
        assertThat(store.claim(owner,job.id(),owner)).isTrue();
        assertThat(store.claim(owner,job.id(),owner)).isFalse();
        assertThat(store.cancel(owner,job.id())).isFalse();
        store.dispatched(other,job.id());
        assertThat(store.find(owner,job.id()).orElseThrow().status()).isEqualTo("DISPATCHING");
        store.dispatched(owner,job.id());
        assertThat(store.find(owner,job.id()).orElseThrow().status()).isEqualTo("DISPATCHED");
        assertThat(store.find(owner,job.id()).orElseThrow().approvedBy()).isEqualTo(owner);
        var cancelled=store.create(owner,CodexWorkflowClient.REPOSITORY,"TESTS","Check tests");
        assertThat(store.cancel(owner,cancelled.id())).isTrue();
        assertThat(store.claim(owner,cancelled.id(),owner)).isFalse();
    }
}
