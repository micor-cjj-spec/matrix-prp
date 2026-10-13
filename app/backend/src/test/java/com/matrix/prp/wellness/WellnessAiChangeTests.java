package com.matrix.prp.wellness;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.ai.AiProviderClient;
import com.matrix.prp.ai.AiSettingsService;
import com.matrix.prp.ai.AiStore;
import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.wellness.WellnessModels.Exercise;
import com.matrix.prp.wellness.WellnessModels.Food;
import java.math.BigDecimal;
import java.time.LocalDate;
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

class WellnessAiChangeTests {
    private final ObjectMapper json=new ObjectMapper();
    private final JdbcTemplate db=mock(JdbcTemplate.class);
    private final WellnessService wellness=mock(WellnessService.class);
    private final AiSettingsService settings=mock(AiSettingsService.class);
    private final AiProviderClient provider=mock(AiProviderClient.class);
    private final AiStore usage=mock(AiStore.class);
    private WellnessAiChangeService service(){
        return new WellnessAiChangeService(db,wellness,json,settings,provider,usage,
            200,1000,250000,1000000);
    }
    @AfterEach void clear(){SecurityContextHolder.clearContext();}
    private void owner(){
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(new UserProfile(17,"test","Test"),null,List.of()));
    }
    private Exercise exercise(int duration) {
        return new Exercise(51,LocalDate.of(2026,10,13),"步行",duration,null,null);
    }
    @Test void disallowsUnknownKindsAndNonWhitelistedActions() {
        assertThatThrownBy(()->WellnessAiChangeService.table("finance"))
            .isInstanceOf(ResponseStatusException.class);
        assertThatThrownBy(()->WellnessAiChangeService.action("exercise","bulk_delete"))
            .isInstanceOf(ResponseStatusException.class);
        assertThat(WellnessAiChangeService.table("metric")).isEqualTo("prp_wellness_body_metrics");
    }
    @Test void createsPrivateDeletePreviewWithoutSendingDataToModel() {
        owner();
        when(wellness.ownedExercise(51)).thenReturn(exercise(30));
        var draft=service().prepare(new WellnessAiChangeService.Request(
            "exercise",51,"delete",""));
        assertThat(draft.action()).isEqualTo("exercise.delete");
        assertThat(draft.before()).containsEntry("durationMinutes",30);
        assertThat(draft.draftId()).isNotBlank();
        verifyNoInteractions(provider,settings,usage);
        verify(db).update(contains("INSERT INTO prp_wellness_ai_drafts"),any(),eq(17L),
            eq("exercise.delete"),any(),any(),any(),any());
    }
    @Test void rejectsUnownedTargetAndDoesNotCreateDraft() {
        owner();
        when(wellness.ownedExercise(99)).thenThrow(new com.matrix.prp.common.api.ResourceNotFoundException("Exercise not found"));
        assertThatThrownBy(()->service().prepare(
            new WellnessAiChangeService.Request("exercise",99,"delete","")))
            .isInstanceOf(com.matrix.prp.common.api.ResourceNotFoundException.class);
        verifyNoInteractions(db,provider);
    }
    @Test void validatesChangedFoodAgainstOwnerScopedReferenceAndRejectsIncorrectFields() throws Exception {
        Food food=new Food(3,"米饭","cooked",new BigDecimal("116"),new BigDecimal("2.6"),
            new BigDecimal("25.9"),new BigDecimal("0.3"),"reference",false);
        when(wellness.accessibleFood(3)).thenReturn(food);
        var svc=service();
        var values=svc.validate("meal",json.readTree("""
            {"date":"2026-10-13","mealType":"LUNCH","note":"",
            "items":[{"foodId":3,"grams":200,"name":"injected"}]}
            """));
        assertThat(json.writeValueAsString(values)).contains("\"name\":\"米饭\"").doesNotContain("injected");
        assertThatThrownBy(()->svc.validate("meal",json.readTree("""
            {"date":"2026-10-13","mealType":"LUNCH","items":[{"foodId":3,"grams":-3}]}
            """))).isInstanceOf(ResponseStatusException.class);
    }
    @Test void staleConfirmationIsRejectedBeforeBusinessMutation() throws Exception {
        owner();
        var svc=service();
        var old=exercise(30);
        when(wellness.ownedExercise(51)).thenReturn(exercise(45));
        var snapshot=Map.of("date","2026-10-13","name","步行","durationMinutes",30);
        String payload=json.writeValueAsString(Map.of("kind","exercise","operation","delete",
            "recordId",51,"before",snapshot,"after",snapshot));
        var row=new java.util.HashMap<String,Object>();
        row.put("action_type","exercise.delete");
        row.put("payload_json",payload);
        row.put("status","PENDING");
        row.put("expires_at",java.sql.Timestamp.valueOf(java.time.LocalDateTime.now().plusMinutes(3)));
        when(db.queryForList(contains("prp_wellness_ai_drafts"),(Object)anyString(),(Object)anyLong())).thenReturn(List.of(row));
        when(db.queryForList(contains("prp_wellness_exercises"),(Object)anyLong(),(Object)anyLong()))
            .thenReturn(List.of(Map.of("id",51L)));
        assertThatThrownBy(()->svc.confirm("123e4567-e89b-12d3-a456-426614174000"))
            .isInstanceOf(ResponseStatusException.class).hasMessageContaining("changed");
        verify(wellness,never()).deleteExercise(anyLong());
    }
}
