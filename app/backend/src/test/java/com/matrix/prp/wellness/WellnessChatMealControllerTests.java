package com.matrix.prp.wellness;

import com.matrix.prp.ai.AiStore;
import com.matrix.prp.auth.model.UserProfile;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class WellnessChatMealControllerTests {
    private static final long USER=77L;
    private void authenticate() {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(
                new UserProfile(USER,"owner","Owner"),null,List.of()));
    }
    @AfterEach void cleanup() {SecurityContextHolder.clearContext();}

    @Test void screenshotRequestUsesSavedConversationInsteadOfFoodlessModelPrompt() {
        authenticate();
        var service=mock(WellnessAiDraftService.class);
        var chat=mock(AiStore.class);
        var controller=new WellnessAiDraftController(service,chat);
        String command="帮我创建一下卡片我录入今天的晚餐";
        when(chat.owns(USER,"current-conversation")).thenReturn(true);
        var history=List.of(
            new AiStore.Message(1,"user","今天晚上吃了楼下炒菜+米饭，饭多菜少",
                LocalDateTime.of(2026,10,14,19,30)));
        when(chat.messages(USER,"current-conversation",null,80)).thenReturn(history);
        var pending=new WellnessAiDraftService.Preview(
            "00000000-0000-0000-0000-000000000001","meal.create",
            "待确认晚餐","conversation/estimate-preview",
            Map.of("date","2026-10-14","mealType","DINNER"),
            "2026-10-14T22:00:00");
        when(service.prepareConversationMeal(history,command)).thenReturn(pending);
        when(chat.append(eq(USER),eq("current-conversation"),eq("assistant"),anyString()))
            .thenReturn(12L);

        var response=controller.chatPrepare(command,null,"current-conversation");
        assertThat(response.data().conversationId()).isEqualTo("current-conversation");
        assertThat(response.data().messageId()).isEqualTo(12L);
        assertThat(response.data().draft().action()).isEqualTo("meal.create");
        verify(service).prepareConversationMeal(history,command);
        verify(service,never()).prepare(eq(command),any());
        verify(chat).saveBlocks(eq(USER),eq("current-conversation"),eq(12L),argThat(blocks->
            blocks.size()==1 && "wellness_draft".equals(blocks.getFirst().type())));
    }

    @Test void oneTwentyAmImportCommandRendersPersistedHealthCardWithoutModelCall(){
        authenticate();
        var service=mock(WellnessAiDraftService.class);
        var chat=mock(AiStore.class);
        var controller=new WellnessAiDraftController(service,chat);
        String command="你帮我导入";
        var history=List.of(
            new AiStore.Message(41,"user",
                "2026-10-14\n晚餐（约650 kcal）\n楼下炒菜（5人两荤两素）＋米饭（饭多菜少）：约650 kcal",
                LocalDateTime.of(2026,10,15,1,15)),
            new AiStore.Message(42,"assistant","你这条格式没有问题，直接录入健康中心即可",
                LocalDateTime.of(2026,10,15,1,17)));
        when(chat.owns(USER,"current-conversation")).thenReturn(true);
        when(chat.messages(USER,"current-conversation",null,80)).thenReturn(history);
        var preview=new WellnessAiDraftService.Preview(
            "00000000-0000-0000-0000-000000000041","meal.create",
            "待确认晚餐","conversation/estimate-preview",
            Map.of("date","2026-10-14","mealType","DINNER"),
            "2026-10-15T01:35:00");
        when(service.prepareConversationMeal(history,command)).thenReturn(preview);
        when(chat.append(eq(USER),eq("current-conversation"),eq("assistant"),anyString()))
            .thenReturn(44L);
        var result=controller.chatPrepare(command,null,"current-conversation");
        assertThat(result.data().draft().draftId()).isEqualTo(preview.draftId());
        assertThat(result.data().messageId()).isEqualTo(44L);
        verify(service).prepareConversationMeal(history,command);
        verify(service,never()).prepare(anyString(),any());
        verify(chat).saveBlocks(eq(USER),eq("current-conversation"),eq(44L),argThat(blocks->
            blocks.size()==1 && "wellness_draft".equals(blocks.getFirst().type())));
    }

    @Test void anotherUsersConversationCannotBeUsedForContextualCard() {
        authenticate();
        var service=mock(WellnessAiDraftService.class);
        var chat=mock(AiStore.class);
        var controller=new WellnessAiDraftController(service,chat);
        assertThatThrownBy(()->controller.chatPrepare(
            "帮我创建一下卡片我录入今天的晚餐",null,"not-owned"))
            .isInstanceOf(ResponseStatusException.class);
        verify(service,never()).prepareConversationMeal(anyList(),anyString());
    }

    @Test void missingConversationGivesActionableErrorWithoutCallingTheModel() {
        authenticate();
        var service=mock(WellnessAiDraftService.class);
        var chat=mock(AiStore.class);
        var controller=new WellnessAiDraftController(service,chat);
        assertThatThrownBy(()->controller.chatPrepare("生成一下卡片",null,null))
            .isInstanceOf(ResponseStatusException.class)
            .hasMessageContaining("请先告诉我吃了什么");
        verify(service,never()).prepare(anyString(),any());
    }
}
