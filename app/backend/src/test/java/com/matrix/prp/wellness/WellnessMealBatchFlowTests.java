package com.matrix.prp.wellness;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.ai.AiSettingsService;
import com.matrix.prp.ai.AiStore;
import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.wellness.WellnessModels.*;
import java.math.BigDecimal;
import java.sql.Timestamp;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class WellnessMealBatchFlowTests {
    private final ObjectMapper json = new ObjectMapper();
    private final LocalDate day = LocalDate.now(ZoneId.of("Asia/Shanghai")).minusDays(1);

    @AfterEach void clear(){ SecurityContextHolder.clearContext(); }
    private void asOwner() {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(
                new UserProfile(71L,"owner","Owner"),"n/a",List.of()));
    }
    private WellnessAiDraftService service(JdbcTemplate db,WellnessService wellness) {
        when(wellness.profile()).thenReturn(new Profile(null,"Asia/Shanghai"));
        return new WellnessAiDraftService(db,wellness,mock(AiSettingsService.class),
            mock(AiStore.class),json,200,1000,250000,1000000);
    }
    private String input() {
        return day+"\n午餐（约1450 kcal）\n红薯排骨：425 kcal\n青椒肉：425 kcal\n汤：150 kcal\n米饭：265 kcal\n泡萝卜：35 kcal\n食用油误差：150 kcal\n"
            +"晚餐（约105 kcal）\n简爱无糖酸奶135g";
    }
    @Test void createsOneOwnerScopedPreviewWithTwoMealsAndNoWrites() {
        asOwner();
        var db=mock(JdbcTemplate.class);
        var wellness=mock(WellnessService.class);
        var draft=service(db,wellness).prepareBatch(input());
        assertThat(draft.action()).isEqualTo("meal.create_batch");
        assertThat(draft.modelUsed()).isEqualTo("system/user-supplied-kcal");
        assertThat(draft.values().get("date")).isEqualTo(day.toString());
        var meals=(List<?>)draft.values().get("meals");
        assertThat(meals).hasSize(2);
        assertThat(meals.toString()).contains("1450","105","简爱无糖酸奶","manualCalories");
        verify(db).update(contains("INSERT INTO prp_wellness_ai_drafts"),any(Object[].class));
        verify(wellness,never()).addAiMeal(any(),anyString(),anyString(),anyList(),anyString());
        verify(wellness,never()).addFood(any());
    }
    @Test void screenshotMessageCreatesExactlyOneDinnerDraftWithoutCallingModelOrSavingMeal() {
        asOwner();
        var db=mock(JdbcTemplate.class);
        var wellness=mock(WellnessService.class);
        var draft=service(db,wellness).prepareBatch(
            "晚餐（约105 kcal）\n简爱无糖酸奶135g帮我录人到昨天的晚餐");
        assertThat(draft.action()).isEqualTo("meal.create_batch");
        assertThat(draft.values().get("date")).isEqualTo(day.toString());
        var meals=(List<?>)draft.values().get("meals");
        assertThat(meals).hasSize(1);
        assertThat(meals.toString()).contains("DINNER","简爱无糖酸奶","135","105")
            .doesNotContain("帮我录人");
        verify(db).update(contains("INSERT INTO prp_wellness_ai_drafts"),any(Object[].class));
        verify(wellness,never()).addAiMeal(any(),anyString(),anyString(),anyList(),anyString());
    }

    @Test void screenshotMessageConflictsWithAnExistingDinnerInsteadOfCreatingDuplicateDraft() {
        asOwner();
        var db=mock(JdbcTemplate.class);
        var wellness=mock(WellnessService.class);
        when(wellness.meals(day)).thenReturn(List.of(new Meal(42L,day,"DINNER","",List.of())));
        assertThatThrownBy(()->service(db,wellness).prepareBatch(
            "晚餐（约105 kcal）\n简爱无糖酸奶135g帮我录入到昨天的晚餐"))
            .isInstanceOf(ResponseStatusException.class)
            .hasMessageContaining("已有记录");
        verify(db,never()).update(contains("INSERT INTO prp_wellness_ai_drafts"),any(Object[].class));
    }

    @Test void aDinnerOnlyFollowupNeverCreatesLunchEvenWhenHistoryContainsBoth() {
        asOwner();
        var db=mock(JdbcTemplate.class);
        var wellness=mock(WellnessService.class);
        var preview=service(db,wellness).prepareBatch(input(),"DINNER");
        assertThat(preview.action()).isEqualTo("meal.create_batch");
        var records=(List<?>)preview.values().get("meals");
        assertThat(records).hasSize(1);
        assertThat(records.toString()).contains("DINNER","105").doesNotContain("LUNCH","1450");
    }

    @Test void skipsAlreadyRecordedLunchButAllowsMissingDinnerInSameDate() {
        asOwner();
        var db=mock(JdbcTemplate.class);
        var wellness=mock(WellnessService.class);
        when(wellness.meals(day)).thenReturn(List.of(new Meal(43L,day,"LUNCH","",List.of())));
        var preview=service(db,wellness).prepareBatch(input());
        var records=(List<?>)preview.values().get("meals");
        assertThat(records).hasSize(1);
        assertThat(records.toString()).contains("DINNER").doesNotContain("LUNCH");
        assertThat(preview.values().get("alreadyExistingTypes").toString()).contains("LUNCH");
    }
    @Test void atomicConfirmWritesBothMealsWithDistinctIdempotencyKeys() throws Exception {
        asOwner();
        var db=mock(JdbcTemplate.class);
        var wellness=mock(WellnessService.class);
        var service=service(db,wellness);
        var draft=service.prepareBatch(input());
        when(db.queryForList(contains("FOR UPDATE"),eq(draft.draftId()),eq(71L)))
            .thenReturn(List.of(Map.of(
                "action_type","meal.create_batch",
                "payload_json",json.writeValueAsString(draft.values()),
                "status","PENDING",
                "expires_at",Timestamp.valueOf(LocalDateTime.now().plusMinutes(10)))));
        when(db.update(anyString(),any(Object[].class))).thenReturn(1);
        when(wellness.addAiMeal(any(),anyString(),anyString(),anyList(),anyString())).thenAnswer(invocation ->
            new Meal("LUNCH".equals(invocation.getArgument(1))?101L:102L,day,
                invocation.getArgument(1),"",List.of()));
        var result=service.confirm(draft.draftId());
        assertThat(result.action()).isEqualTo("meal.create_batch");
        assertThat((List<?>)result.saved()).hasSize(2);
        verify(wellness).addAiMeal(eq(day),eq("LUNCH"),anyString(),anyList(),eq(draft.draftId()+"-0"));
        verify(wellness).addAiMeal(eq(day),eq("DINNER"),anyString(),anyList(),eq(draft.draftId()+"-1"));
        verify(db).update(contains("status='CONSUMED'"),eq(draft.draftId()),eq(71L));
        verify(wellness,never()).addFood(any());
    }
    @Test void duplicateFoundAtConfirmStopsEntireBatch() throws Exception {
        asOwner();
        var db=mock(JdbcTemplate.class);
        var wellness=mock(WellnessService.class);
        var service=service(db,wellness);
        var draft=service.prepareBatch(input());
        when(db.queryForList(contains("FOR UPDATE"),eq(draft.draftId()),eq(71L)))
            .thenReturn(List.of(Map.of(
                "action_type","meal.create_batch",
                "payload_json",json.writeValueAsString(draft.values()),
                "status","PENDING",
                "expires_at",Timestamp.valueOf(LocalDateTime.now().plusMinutes(10)))));
        when(wellness.meals(day)).thenReturn(List.of(new Meal(91L,day,"DINNER","",List.of())));
        assertThatThrownBy(()->service.confirm(draft.draftId()))
            .isInstanceOf(ResponseStatusException.class)
            .hasMessageContaining("目标日期已有相同餐次");
        verify(wellness,never()).addAiMeal(any(),anyString(),anyString(),anyList(),anyString());
        verify(db,never()).update(contains("status='CONSUMED'"),any(Object[].class));
    }
    @Test void directMealWriterUsesSameOwnerRowLockAndRejectsDuplicateSlot() {
        asOwner();
        var db=mock(JdbcTemplate.class);
        var service=new WellnessService(db);
        when(db.query(contains("AND id<>? LIMIT 1"),
            any(org.springframework.jdbc.core.RowMapper.class),
            eq(71L),eq(day),eq("DINNER"),eq(-1L))).thenReturn(List.of(901L));
        var item=new WellnessService.AiMealItem(null,"简爱无糖酸奶",
            new BigDecimal("135"),new BigDecimal("105"));
        assertThatThrownBy(()->service.addAiMeal(day,"DINNER","",List.of(item),"unique-draft-key"))
            .isInstanceOf(ResponseStatusException.class)
            .hasMessageContaining("避免重复记录");
        verify(db).queryForObject(contains("FOR UPDATE"),eq(Long.class),eq(71L));
        verify(db,never()).update(contains("INSERT INTO prp_wellness_meals"),any(Object[].class));
    }

    @Test void conversationalYesIsGroundedInConfirmedDraftAndReportsNoPendingOtherwise() {
        asOwner();
        var chat=mock(AiStore.class);
        var service=mock(WellnessAiDraftService.class);
        var ctrl=new WellnessAiDraftController(service,chat);
        String conv="conversation-test";
        String id="12345678-1234-1234-1234-123456789abc";
        when(chat.owns(71L,conv)).thenReturn(true);
        when(chat.blocks(71L,conv)).thenReturn(List.of(new AiStore.MessageBlock(
            50L,"wellness_draft","wellness","待确认健康记录",id)));
        var preview=new WellnessAiDraftService.Preview(id,"meal.create_batch","multi",
            "system/user",Map.of("date",day.toString()),LocalDateTime.now().plusMinutes(10).toString());
        when(service.getDraft(id)).thenReturn(new WellnessAiDraftService.DraftView(preview,"PENDING"));
        when(service.confirm(id)).thenReturn(new WellnessAiDraftService.Outcome("meal.create_batch",
            List.of(new Meal(12L,day,"LUNCH","",List.of()),new Meal(13L,day,"DINNER","",List.of())),
            "/wellness?date="+day));
        when(chat.append(eq(71L),eq(conv),anyString(),anyString())).thenReturn(51L);
        var result=ctrl.confirmPending(new WellnessAiDraftController.ChatConfirmationRequest(conv,"确认保存"))
            .data();
        assertThat(result.status()).isEqualTo("SAVED");
        assertThat(result.content()).contains("记录ID 12","记录ID 13");
        verify(service).confirm(id);
        when(chat.blocks(71L,conv)).thenReturn(List.of());
        var noPending=ctrl.confirmPending(new WellnessAiDraftController.ChatConfirmationRequest(conv,"是的"))
            .data();
        assertThat(noPending.status()).isEqualTo("NO_PENDING");
        verify(service,times(1)).confirm(id);
    }

    @Test void structuredMealAcceptsThirtyItemsAndRejectsThirtyOne() {
        asOwner();
        var db=mock(JdbcTemplate.class);
        var wellness=mock(WellnessService.class);
        var service=service(db,wellness);
        for(int count:new int[]{8,30}) {
            StringBuilder input=new StringBuilder(day+"\n晚餐\n");
            for(int i=1;i<=count;i++)input.append("食材").append(i).append("：10 kcal\n");
            var draft=service.prepareBatch(input.toString());
            var groups=(List<?>)draft.values().get("meals");
            assertThat(groups.toString()).contains("食材"+count);
        }
        StringBuilder tooMany=new StringBuilder(day+"\n晚餐\n");
        for(int i=1;i<=31;i++)tooMany.append("食材").append(i).append("：10 kcal\n");
        assertThatThrownBy(()->service.prepareBatch(tooMany.toString()))
            .isInstanceOf(ResponseStatusException.class)
            .hasMessageContaining("最多30项");
    }

    @Test void chatContextCreatesOneCardItemPerExplicitFoodWithoutInventingCalories() {
        asOwner();
        var db=mock(JdbcTemplate.class);
        var wellness=mock(WellnessService.class);
        var service=service(db,wellness);
        String ingredients=java.util.stream.IntStream.rangeClosed(1,30)
            .mapToObj(i->"食材"+i).collect(java.util.stream.Collectors.joining("、"));
        var message=new AiStore.Message(1,"user",day+" 晚餐吃了火锅："+ingredients,
            LocalDateTime.now().minusDays(1));
        var preview=service.prepareConversationMeal(List.of(message),"帮我生成昨天晚餐卡片");
        var items=(List<?>)preview.values().get("items");
        assertThat(items).hasSize(30);
        assertThat(items.toString()).contains("食材1","食材30","catalog")
            .doesNotContain("manualCalories=650");
        assertThat(preview.values().get("note").toString()).contains("逐项检查");
        verify(wellness,never()).addAiMeal(any(),anyString(),anyString(),anyList(),anyString());
        String tooMany=java.util.stream.IntStream.rangeClosed(1,31)
            .mapToObj(i->"食材"+i).collect(java.util.stream.Collectors.joining("、"));
        var overflow=new AiStore.Message(2,"user",day+" 晚餐吃了火锅："+tooMany,
            LocalDateTime.now().minusDays(1));
        assertThatThrownBy(()->service.prepareConversationMeal(List.of(overflow),"帮我生成昨天晚餐卡片"))
            .isInstanceOf(ResponseStatusException.class)
            .hasMessageContaining("超过30项");
    }

}
