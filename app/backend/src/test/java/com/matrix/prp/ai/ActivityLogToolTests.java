package com.matrix.prp.ai;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.activity.ActivityLogStore;
import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.finance.service.FinanceService;
import com.matrix.prp.practice.PracticeService;
import com.matrix.prp.tasks.service.TaskService;
import com.matrix.prp.wellness.WellnessService;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
class ActivityLogToolTests {
    @AfterEach void clear(){SecurityContextHolder.clearContext();}
    @SuppressWarnings("unchecked")
    @Test void requiresConsentAndAlwaysUsesCurrentJwtOwner() throws Exception {
        long owner=48151L;
        SecurityContextHolder.getContext().setAuthentication(new UsernamePasswordAuthenticationToken(
            new UserProfile(owner,"logs","Logs"),null,List.of()));
        TaskService tasks=mock(TaskService.class);
        ActivityLogStore logs=mock(ActivityLogStore.class);
        when(logs.recent(eq(owner),eq(7),eq(20))).thenReturn(List.of(
            new ActivityLogStore.Entry("HTTP","GET /api/tasks", "200",200,13,LocalDateTime.now())));
        AiToolRegistry registry=new AiToolRegistry(tasks,mock(ObjectProvider.class),
            mock(ObjectProvider.class),mock(FinanceService.class),new AiNavigationResolver(tasks),logs);
        var args=new ObjectMapper().readTree("{\"days\":7,\"userId\":9999}");
        assertThatThrownBy(()->registry.execute("activity_recent",new ObjectMapper().readTree("{}"),Set.of()))
            .isInstanceOf(ResponseStatusException.class);
        verifyNoInteractions(logs);
        assertThat(registry.definitions(Set.of("activity_logs")).stream().map(AiToolRegistry.Definition::name))
            .contains("activity_recent");
        var found=registry.execute("activity_recent",new ObjectMapper().readTree("{\"days\":7}"),Set.of("activity_logs"));
        assertThat(found.data().toString()).contains("GET /api/tasks");
        verify(logs).recent(owner,7,20);
        assertThatThrownBy(()->registry.execute("activity_recent",
            new ObjectMapper().readTree("{\"days\":365}"),Set.of("activity_logs")))
            .isInstanceOf(ResponseStatusException.class);
    }
}
