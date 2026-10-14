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
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class WellnessMealRepeatTests {
    private final ObjectMapper mapper=new ObjectMapper();

    @AfterEach void clearIdentity(){ SecurityContextHolder.clearContext(); }

    private void asUser(){
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(
                new UserProfile(71L,"repeat-owner","Repeat Owner"),"n/a",List.of()));
    }

    private Meal meal(long id,LocalDate date) {
        return new Meal(id,date,"BREAKFAST","no added sugar",List.of(
            new MealItem(10L,101L,"鸡蛋",new BigDecimal("100"),
                new BigDecimal("144"),new BigDecimal("13.3"),BigDecimal.ZERO,BigDecimal.ZERO,true),
            new MealItem(11L,102L,"牛奶",new BigDecimal("200"),
                new BigDecimal("124"),new BigDecimal("6.4"),BigDecimal.ZERO,BigDecimal.ZERO,true)
        ));
    }

    private WellnessAiDraftService service(JdbcTemplate db,WellnessService wellness) {
        when(wellness.profile()).thenReturn(new Profile(null,"Asia/Shanghai"));
        return new WellnessAiDraftService(db,wellness,mock(AiSettingsService.class),
            mock(AiStore.class),mapper,200,1000,250000,1000000);
    }

    @Test void parsesYesterdayAndDayBeforeWithoutUsingTheModel() {
        LocalDate now=LocalDate.of(2026,10,14);
        var parsed=WellnessMealRepeatIntent.parse(
            "我昨天和前天的早餐也是这样吃的，也帮我记录一下",now).orElseThrow();
        assertThat(parsed.mealType()).isEqualTo("BREAKFAST");
        assertThat(parsed.targets()).containsExactly(now.minusDays(2),now.minusDays(1));
        assertThat(WellnessMealRepeatIntent.parse(
            "帮我分析早餐热量",now)).isEmpty();
        assertThat(WellnessMealRepeatIntent.parse(
            "昨天早餐不一样，吃了鸡蛋",now)).isEmpty();
        assertThat(WellnessMealRepeatIntent.parse(
            "昨天和前天的早餐不要复制今天的",now)).isEmpty();
        assertThat(WellnessMealRepeatIntent.parse(
            "昨天早餐不同于今天，不要按今天早餐记录",now)).isEmpty();
        assertThat(WellnessMealRepeatIntent.parse(
            "把今天早餐复制到昨天",now).orElseThrow().targets())
            .containsExactly(now.minusDays(1));
        assertThat(WellnessMealRepeatIntent.parse(
            "最近三天的午餐和上次一样",now).orElseThrow().targets())
            .containsExactly(now.minusDays(3),now.minusDays(2),now.minusDays(1));
        assertThat(WellnessMealRepeatIntent.parse(
            "复制早餐到2099-01-01",now)).isEmpty();
        assertThat(WellnessMealRepeatIntent.parse(
            "把早餐复制到2026-10-10、2026-10-11",now).orElseThrow().targets())
            .containsExactly(now.minusDays(4),now.minusDays(3));
    }

    @Test void copiesOnlyCurrentUsersSavedSourceIntoTwoUncommittedTargets() throws Exception {
        asUser();
        LocalDate today=LocalDate.now(java.time.ZoneId.of("Asia/Shanghai"));
        var source=meal(91L,today);
        JdbcTemplate db=mock(JdbcTemplate.class);
        WellnessService wellness=mock(WellnessService.class);
        when(wellness.recentMeals(eq("BREAKFAST"),eq(today),eq(31)))
            .thenReturn(List.of(source));
        var service=service(db,wellness);
        var preview=service.prepareRepeat("昨天和前天早餐也是这样吃的，请记录");
        assertThat(preview.action()).isEqualTo("meal.copy_batch");
        assertThat(preview.values().get("sourceMealId")).isEqualTo(91L);
        assertThat(preview.values().get("targets")).isEqualTo(
            List.of(today.minusDays(2).toString(),today.minusDays(1).toString()));
        assertThat(preview.values().get("items").toString())
            .contains("鸡蛋","牛奶");
        verify(db).update(contains("INSERT INTO prp_wellness_ai_drafts"),any(Object[].class));
        verify(wellness,never()).addMeal(any());
    }

    @Test void blocksDuplicatesBeforeDraftCreation() {
        asUser();
        LocalDate today=LocalDate.now(java.time.ZoneId.of("Asia/Shanghai"));
        JdbcTemplate db=mock(JdbcTemplate.class);
        WellnessService wellness=mock(WellnessService.class);
        when(wellness.recentMeals(eq("BREAKFAST"),eq(today),eq(31)))
            .thenReturn(List.of(meal(91L,today)));
        when(wellness.meals(today.minusDays(1))).thenReturn(List.of(meal(92L,today.minusDays(1))));
        var service=service(db,wellness);
        assertThatThrownBy(()->service.prepareRepeat("昨天前天早餐也是一样，请记录"))
            .isInstanceOf(ResponseStatusException.class).hasMessageContaining("已有同类型餐次");
        verify(db,never()).update(anyString(),any(Object[].class));
    }

    @Test void confirmationChecksCurrentSourceAndWritesBothMealsWithDistinctIdempotencyKeys() throws Exception {
        asUser();
        LocalDate today=LocalDate.now(java.time.ZoneId.of("Asia/Shanghai"));
        var source=meal(91L,today);
        JdbcTemplate db=mock(JdbcTemplate.class);
        WellnessService wellness=mock(WellnessService.class);
        var service=service(db,wellness);
        var values=Map.of(
            "date",today.minusDays(2).toString(),
            "sourceDate",today.toString(),
            "sourceMealId",91L,
            "mealType","BREAKFAST",
            "targets",List.of(today.minusDays(2).toString(),today.minusDays(1).toString()),
            "items",List.of(Map.of("foodId",101L,"grams",100),
                Map.of("foodId",102L,"grams",200))
        );
        String draftId="12345678-1234-1234-1234-123456789abc";
        when(db.queryForList(contains("FROM prp_wellness_ai_drafts"),eq(draftId),eq(71L)))
            .thenReturn(List.of(Map.of("action_type","meal.copy_batch","payload_json",mapper.writeValueAsString(values),
                "status","PENDING","expires_at",Timestamp.valueOf(LocalDateTime.now().plusMinutes(10)))));
        when(db.update(anyString(),any(Object[].class))).thenReturn(1);
        when(wellness.ownedMeal(91L)).thenReturn(source);
        when(wellness.addMeal(any())).thenAnswer(inv->{
            MealInput in=inv.getArgument(0);
            return new Meal(90L,in.mealDate(),in.mealType(),in.note(),List.of());
        });
        var confirmed=service.confirm(draftId);
        assertThat(confirmed.action()).isEqualTo("meal.copy_batch");
        assertThat((List<?>)confirmed.saved()).hasSize(2);
        var captured=org.mockito.ArgumentCaptor.forClass(MealInput.class);
        verify(wellness,times(2)).addMeal(captured.capture());
        assertThat(captured.getAllValues().stream().map(MealInput::mealDate))
            .containsExactly(today.minusDays(2),today.minusDays(1));
        assertThat(captured.getAllValues().stream().map(MealInput::idempotencyKey))
            .containsExactly(draftId+"-0",draftId+"-1");
        verify(db).update(contains("status='CONSUMED'"),eq(draftId),eq(71L));
    }

    @Test void preventsAnyWritesIfTheSourceChangedSincePreview() throws Exception {
        asUser();
        LocalDate today=LocalDate.now(java.time.ZoneId.of("Asia/Shanghai"));
        JdbcTemplate db=mock(JdbcTemplate.class);
        WellnessService wellness=mock(WellnessService.class);
        var service=service(db,wellness);
        String id="12345678-1234-1234-1234-123456789abc";
        var values=Map.of(
            "date",today.minusDays(1).toString(),"sourceDate",today.toString(),
            "sourceMealId",91L,"mealType","BREAKFAST",
            "targets",List.of(today.minusDays(1).toString()),
            "items",List.of(Map.of("foodId",101L,"grams",200),
                Map.of("foodId",102L,"grams",200))
        );
        when(db.queryForList(contains("FROM prp_wellness_ai_drafts"),eq(id),eq(71L)))
            .thenReturn(List.of(Map.of("action_type","meal.copy_batch","payload_json",mapper.writeValueAsString(values),
                "status","PENDING","expires_at",Timestamp.valueOf(LocalDateTime.now().plusMinutes(10)))));
        when(wellness.ownedMeal(91L)).thenReturn(meal(91L,today)); // actual 100g, preview says 200g
        assertThatThrownBy(()->service.confirm(id))
            .isInstanceOf(ResponseStatusException.class).hasMessageContaining("份量已改变");
        verify(wellness,never()).addMeal(any());
    }
}
