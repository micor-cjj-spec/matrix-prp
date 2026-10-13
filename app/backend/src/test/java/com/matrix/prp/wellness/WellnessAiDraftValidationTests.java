package com.matrix.prp.wellness;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.ai.AiSettingsService;
import com.matrix.prp.ai.AiStore;
import com.matrix.prp.wellness.WellnessModels.Food;
import com.matrix.prp.wellness.WellnessModels.Profile;
import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class WellnessAiDraftValidationTests {
    private final ObjectMapper json=new ObjectMapper();
    private WellnessAiDraftService service(WellnessService foods) {
        when(foods.profile()).thenReturn(new Profile(null,"Asia/Shanghai"));
        return new WellnessAiDraftService(mock(JdbcTemplate.class),foods,
            mock(AiSettingsService.class),mock(AiStore.class),json,200,1000,250000,1000000);
    }
    @Test void unresolvedFoodBecomesEditableNotFabricatedNutrition() throws Exception {
        WellnessService foods=mock(WellnessService.class);
        when(foods.foods(anyString())).thenReturn(List.of());
        var service=service(foods);
        var draft=service.verify(json.readTree("""
            {"action":"meal.create","date":"2026-10-13","mealType":"LUNCH",
            "items":[{"name":"红油馄饨","grams":0}],"note":"estimated serving"}
            """));
        var item=((List<?>)draft.get("items")).getFirst();
        assertThat(json.writeValueAsString(item)).contains("\"foodId\":0")
            .contains("\"calories\":null").contains("\"grams\":0");
    }
    @Test void editedFoodIdIsCheckedFromOwnedOrSharedCatalogAndNutrientsRecomputed() throws Exception {
        WellnessService foods=mock(WellnessService.class);
        when(foods.accessibleFood(12L)).thenReturn(new Food(12L,"米饭","cooked",
            new BigDecimal("116"),new BigDecimal("2.6"),new BigDecimal("25.9"),
            new BigDecimal("0.3"),"test",false));
        var service=service(foods);
        var draft=service.verify(json.readTree("""
            {"action":"meal.create","date":"2026-10-13","mealType":"LUNCH",
            "items":[{"name":"fake","foodId":12,"grams":200,"calories":9999}]}
            """),true);
        assertThat(json.writeValueAsString(draft)).contains("\"name\":\"米饭\"")
            .contains("\"calories\":232");
        verify(foods).accessibleFood(12L);
    }
    @Test void normalizesWhitespaceButNotDifferentFoodDescriptions() {
        assertThat(WellnessAiDraftService.normalize("米 饭（熟）"))
            .isEqualTo("米饭熟");
        assertThat(WellnessAiDraftService.normalize("红油馄饨"))
            .isNotEqualTo(WellnessAiDraftService.normalize("清汤馄饨"));
    }
}
