package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.ai.CodexWorkflowClient;
import com.matrix.prp.ai.CodexJobStore;
import java.time.LocalDateTime;
import org.junit.jupiter.api.Test;

class CodexWorkflowClientTests {
    private final ObjectMapper json=new ObjectMapper();
    @Test void rejectsUnsafeOrUnconfiguredDispatch() {
        String token="test-token-longer-than-20-characters";
        var off=new CodexWorkflowClient(json,false,token,CodexWorkflowClient.REPOSITORY);
        var wrongRepo=new CodexWorkflowClient(json,true,token,"someone/other-repository");
        var emptyToken=new CodexWorkflowClient(json,true,"",CodexWorkflowClient.REPOSITORY);
        assertThat(off.configured()).isFalse();
        assertThat(wrongRepo.configured()).isFalse();
        assertThat(emptyToken.configured()).isFalse();
        var job=new CodexJobStore.Job("00000000-0000-0000-0000-000000000000",
            1,CodexWorkflowClient.REPOSITORY,"FIX","Test","PENDING_APPROVAL",
            null,null,null,LocalDateTime.now(),LocalDateTime.now());
        assertThatThrownBy(()->off.dispatch(job)).isInstanceOf(Exception.class);
        assertThatThrownBy(()->wrongRepo.dispatch(job)).isInstanceOf(Exception.class);
    }
}
