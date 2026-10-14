package com.matrix.prp.wellness;

import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.wellness.WellnessModels.*;
import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import com.matrix.prp.common.api.ResourceNotFoundException;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class WellnessDishTemplateTests {
    @AfterEach void clearIdentity(){ SecurityContextHolder.clearContext(); }
    private void asUser(long id){
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(new UserProfile(id,"owner","Owner"),"n/a",List.of()));
    }
    @Test void lookupOnlyReadsAuthenticatedOwnersTemplateAndNeverReadsGlobalFoodCatalog() {
        asUser(19);
        JdbcTemplate db=mock(JdbcTemplate.class);
        WellnessService service=new WellnessService(db);
        assertThatThrownBy(()->service.ownedDishTemplate(7))
            .isInstanceOf(ResourceNotFoundException.class);
        verify(db).query(contains("FROM prp_wellness_dish_templates"),
            any(org.springframework.jdbc.core.RowMapper.class),eq(7L),eq(19L));
        verify(db,never()).update(contains("prp_wellness_foods"),any(Object[].class));
    }
    @Test void rejectsInvalidCalorieOrUnlabelledSourceAndRequiresExplicitOwner() {
        asUser(19);
        WellnessService service=new WellnessService(mock(JdbcTemplate.class));
        assertThatThrownBy(()->service.saveDishTemplate(new DishTemplateInput(
            "楼下沙县小吃","红油馄饨","大碗",17,new BigDecimal("0"),"AI_ESTIMATE","来自GPT")))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(()->service.saveDishTemplate(new DishTemplateInput(
            "楼下沙县小吃","红油馄饨","大碗",17,new BigDecimal("650"),"TRUST_ME","来自GPT")))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(()->service.dishTemplates("x".repeat(101)))
            .isInstanceOf(IllegalArgumentException.class);
    }
    @Test void deletionIsUserScopedAndDoesNotDeleteHistoricalMealSnapshots() {
        asUser(19);
        JdbcTemplate db=mock(JdbcTemplate.class);
        when(db.update(contains("DELETE FROM prp_wellness_dish_templates"),eq(7L),eq(19L)))
            .thenReturn(1);
        new WellnessService(db).deleteDishTemplate(7L);
        verify(db,never()).update(contains("prp_wellness_meal_items"),any(Object[].class));
        verify(db,never()).update(contains("prp_wellness_foods"),any(Object[].class));
    }
    @Test void personalDishModelsKeepPerServingEstimateWithProvenance() {
        var input=new DishTemplateInput("楼下沙县小吃","红油馄饨","大碗",17,
            new BigDecimal("650.00"),"AI_ESTIMATE","和 ChatGPT 沟通后的估算");
        assertThat(input.portionCount()).isEqualTo(17);
        assertThat(input.caloriesPerServing()).isEqualByComparingTo("650.00");
        assertThat(input.sourceType()).isEqualTo("AI_ESTIMATE");
    }
}
