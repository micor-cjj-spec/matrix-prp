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
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class WellnessManualCalorieTests {
    private final ObjectMapper json = new ObjectMapper();
    @AfterEach void clearIdentity() { SecurityContextHolder.clearContext(); }
    private void asUser() {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(
                new UserProfile(71L,"user71","User 71"),"n/a",List.of()));
    }
    private WellnessAiDraftService service(JdbcTemplate db, WellnessService wellness) {
        when(wellness.profile()).thenReturn(new Profile(null,"Asia/Shanghai"));
        return new WellnessAiDraftService(db,wellness,mock(AiSettingsService.class),
            mock(AiStore.class),json,200,1000,250000,1000000);
    }

    @Test void manualCalorieOnlyIsValidatedAndNeverAcceptedFromModelJson() throws Exception {
        WellnessService wellness=mock(WellnessService.class);
        var draftService=service(mock(JdbcTemplate.class),wellness);
        var modelOutput=json.readTree("""
          {"action":"meal.create","date":"2026-10-12","mealType":"LUNCH",
           "items":[{"name":"红油馄饨","grams":0,"mode":"manual","manualCalories":650}]}
          """);
        var untrusted=draftService.verify(modelOutput);
        assertThat(untrusted.get("items").toString()).contains("manualCalories=null","calories=null");
        var edited=draftService.verify(modelOutput,true);
        assertThat(edited.get("items").toString()).contains("manualCalories=650","calories=650","mode=manual");
        verify(wellness,never()).addFood(any());
    }

    @Test void parsesOnlyCaloriesExplicitlyProvidedByUserAndSingleFood() throws Exception {
        assertThat(WellnessAiDraftService.userProvidedCalories(
            "我星期一中午吃的红油馄饨 热量大概650千卡，帮我记录一下"))
            .isEqualByComparingTo("650");
        assertThat(WellnessAiDraftService.userProvidedCalories("吃了200克红油馄饨"))
            .isNull();
        assertThat(WellnessAiDraftService.userProvidedCalories("食物A 100千卡，食物B 200千卡"))
            .isNull();
        var service=service(mock(JdbcTemplate.class),mock(WellnessService.class));
        var values=service.verify(json.readTree("""
          {"action":"meal.create","date":"2026-10-12","mealType":"LUNCH",
           "items":[{"name":"红油馄饨","grams":0}]}
          """));
        WellnessAiDraftService.applyUserCalorieEstimate(values,
            "星期一午餐红油馄饨约650千卡，帮我记下来");
        assertThat(values.get("items").toString()).contains("manualCalories=650","mode=manual","foodId=0");
    }

    @Test void rejectsMissingNegativeAndExcessiveCustomCalories() throws Exception {
        var service=service(mock(JdbcTemplate.class),mock(WellnessService.class));
        for(String calories:List.of("0","-20","20001","650.123","null")) {
            String source="{\"action\":\"meal.create\",\"date\":\"2026-10-12\",\"mealType\":\"LUNCH\","+
                "\"items\":[{\"name\":\"馄饨\",\"mode\":\"manual\",\"grams\":0,\"manualCalories\":"+calories+"}]}";
            assertThatThrownBy(()->service.verify(json.readTree(source),true))
                .isInstanceOf(ResponseStatusException.class);
        }
    }

    @Test void confirmStoresUserTotalInMealSnapshotNotFoodCatalog() throws Exception {
        asUser();
        JdbcTemplate db=mock(JdbcTemplate.class);
        WellnessService wellness=mock(WellnessService.class);
        var service=service(db,wellness);
        String draftId="12345678-1234-1234-1234-123456789abc";
        var payload=Map.of(
            "date","2026-10-12","mealType","LUNCH","note","用户估算650千卡",
            "items",List.of(Map.of("foodId",0,"mode","manual",
                "name","红油馄饨","grams",0,"manualCalories",650))
        );
        when(db.queryForList(contains("FROM prp_wellness_ai_drafts"),eq(draftId),eq(71L)))
            .thenReturn(List.of(Map.of("action_type","meal.create",
                "payload_json",json.writeValueAsString(payload),"status","PENDING",
                "expires_at",Timestamp.valueOf(LocalDateTime.now().plusMinutes(10)))));
        when(db.update(anyString(),any(Object[].class))).thenReturn(1);
        when(wellness.addAiMeal(any(),anyString(),anyString(),anyList(),eq(draftId)))
            .thenReturn(new Meal(500L,LocalDate.of(2026,10,12),"LUNCH","",List.of()));
        var result=service.confirm(draftId);
        assertThat(result.action()).isEqualTo("meal.create");
        var rows=ArgumentCaptor.forClass(List.class);
        verify(wellness).addAiMeal(eq(LocalDate.of(2026,10,12)),eq("LUNCH"),contains("用户自定义热量"),
            rows.capture(),eq(draftId));
        var item=(WellnessService.AiMealItem)rows.getValue().getFirst();
        assertThat(item.foodId()).isNull();
        assertThat(item.name()).isEqualTo("红油馄饨");
        assertThat(item.grams()).isEqualByComparingTo("0");
        assertThat(item.calories()).isEqualByComparingTo("650");
        verify(wellness,never()).addFood(any());
        verify(wellness,never()).addMeal(any());
        verify(db).update(contains("status='CONSUMED'"),eq(draftId),eq(71L));
    }
}
