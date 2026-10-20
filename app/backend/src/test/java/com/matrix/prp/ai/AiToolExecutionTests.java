package com.matrix.prp.ai;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.finance.service.FinanceService;
import com.matrix.prp.practice.PracticeService;
import com.matrix.prp.tasks.model.TaskFilter;
import com.matrix.prp.tasks.model.TaskItem;
import com.matrix.prp.tasks.service.TaskService;
import com.matrix.prp.wellness.WellnessService;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Consumer;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.mock.env.MockEnvironment;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class AiToolExecutionTests {
    private final ObjectMapper json = new ObjectMapper();

    @AfterEach void clear() { SecurityContextHolder.clearContext(); }

    @SuppressWarnings("unchecked")
    @Test void executesOnlyApprovedReadToolsAndPersistsOwnedCards() throws Exception {
        long owner=4242L;
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(new UserProfile(owner,"reader","Reader"),null,List.of()));
        TaskService taskService=mock(TaskService.class);
        when(taskService.listLimited(any(TaskFilter.class), eq(20))).thenReturn(List.of(new TaskItem(
            17L,"learning","My private task","secret details","medium","todo",
            LocalDate.of(2026,10,14),null,null)));
        ObjectProvider<PracticeService> practice=mock(ObjectProvider.class);
        ObjectProvider<WellnessService> wellness=mock(ObjectProvider.class);
        FinanceService finance=mock(FinanceService.class);
        AiNavigationResolver navigation=new AiNavigationResolver(taskService);
        AiToolRegistry tools=new AiToolRegistry(taskService,practice,wellness,finance,navigation);

        assertThatThrownBy(()->tools.execute("finance_monthly",json.readTree("{}"),Set.of("tasks")))
            .isInstanceOf(ResponseStatusException.class);
        verifyNoInteractions(finance);
        assertThat(tools.definitions(Set.of()).stream().map(AiToolRegistry.Definition::name).toList())
            .containsExactly("navigation_open");

        InMemoryAiStore store=new InMemoryAiStore();
        DeepSeekClient model=mock(DeepSeekClient.class);
        AtomicReference<List<DeepSeekClient.ChatMessage>> sentToModel=new AtomicReference<>();
        when(model.model()).thenReturn("deepseek-chat");
        when(model.stream(anyList(),anyInt(),any())).thenAnswer(inv->{
            sentToModel.set(List.copyOf(inv.getArgument(0)));
            Consumer<String> stream=inv.getArgument(2);
            stream.accept("One task found.");
            return new DeepSeekClient.Result("One task found.",15,5);
        });
        AiSettingsService settings=mock(AiSettingsService.class);
        when(settings.selection(owner)).thenReturn(new AiSettingsStore.Selection("deepseek","deepseek-chat"));
        when(settings.resolve(owner)).thenReturn(new AiSettingsService.Runtime(
            AiProviderCatalog.require("deepseek"),"deepseek-chat","test-only-key",true));
        AiContextConsentService consent=mock(AiContextConsentService.class);
        var snapshot=new AiContextService.Snapshot(List.of("tasks"),LocalDate.now(),Map.of());
        when(consent.consume("approved-once",List.of("tasks"))).thenReturn(snapshot);
        when(consent.augment(anyString(),eq(snapshot))).thenReturn("find my task");
        AiToolPlanner planner=mock(AiToolPlanner.class);
        when(planner.plan(any(),anyList(),anyList())).thenReturn(List.of(
            new AiToolPlanner.Call("tasks_list",json.readTree("{}"))));
        AiToolAudit audit=mock(AiToolAudit.class);
        AiModelGateway gateway=new DefaultAiModelGateway(model,mock(AiProviderClient.class));
        var service=new AiService(store,gateway,settings,consent,
            planner,tools,audit,json,new MockEnvironment(),Runnable::run,
            1024,200,1000,250000L,1000000L);

        service.chat(null,"find my task",List.of("tasks"),"approved-once");
        var conversation=store.list(owner).getFirst();
        assertThat(store.messages(owner,conversation.id()).stream().map(AiStore.Message::content).toList())
            .contains("One task found.");
        assertThat(store.blocks(owner,conversation.id())).hasSize(1);
        assertThat(store.blocks(owner,conversation.id()).getFirst().route()).isEqualTo("/tasks");
        verify(audit).record(eq(owner),eq(conversation.id()),eq("tasks_list"),eq("tasks"),
            eq("SUCCESS"),anyLong());
        // Even a known ID from another user's conversation is not readable.
        assertThat(store.blocks(owner+1,conversation.id())).isEmpty();
        assertThat(sentToModel.get().stream().filter(m->m.role().equals("system"))
            .map(DeepSeekClient.ChatMessage::content)).noneMatch(s->s.contains("My private task"));
        assertThat(sentToModel.get().stream().filter(m->m.role().equals("user"))
            .map(DeepSeekClient.ChatMessage::content)).anyMatch(s ->
                s.contains("[PRP_REFERENCE_DATA]") && s.contains("My private task"));
    }
}
