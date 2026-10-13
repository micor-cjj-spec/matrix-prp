package com.matrix.prp.wellness;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import java.math.BigDecimal;
import static org.assertj.core.api.Assertions.*;

class UsdaFoodCatalogTests {
    private final ObjectMapper json = new ObjectMapper();

    @Test void parsesUsdaSearchFieldsByNumberAndKcalUnit() throws Exception {
        var food = UsdaFoodCatalog.parse(json.readTree("""
            {"fdcId":173944,"description":"Banana, raw","foodNutrients":[
                {"number":1008,"amount":89,"unitName":"kcal"},
                {"number":1003,"amount":1.09,"unitName":"g"},
                {"number":1005,"amount":22.84,"unitName":"g"},
                {"number":1004,"amount":0.33,"unitName":"g"}]}
            """));
        assertThat(food).isNotNull();
        assertThat(food.fdcId()).isEqualTo(173944);
        assertThat(food.calories100g()).isEqualByComparingTo(new BigDecimal("89"));
        assertThat(food.carbs100g()).isEqualByComparingTo(new BigDecimal("22.84"));
    }
    @Test void parsesDetailsNutrientObjectsAndFoundationEnergy() throws Exception {
        var food=UsdaFoodCatalog.parse(json.readTree("""
            {"fdcId":77,"description":"Test cheese","foodNutrients":[
                {"nutrient":{"id":2047,"unitName":"kcal"},"amount":150},
                {"nutrient":{"id":1003,"unitName":"g"},"amount":12},
                {"nutrient":{"id":1005,"unitName":"g"},"amount":4},
                {"nutrient":{"id":1004,"unitName":"g"},"amount":8}]}
            """));
        assertThat(food).isNotNull();
        assertThat(food.calories100g()).isEqualByComparingTo(new BigDecimal("150"));
    }
    @Test void rejectsKilojoulesAndIncompleteNutrients() throws Exception {
        var food=UsdaFoodCatalog.parse(json.readTree("""
            {"fdcId":1,"description":"Test","foodNutrients":[
                {"number":1008,"amount":1000,"unitName":"kJ"},
                {"number":1003,"amount":1,"unitName":"g"},
                {"number":1005,"amount":2,"unitName":"g"},
                {"number":1004,"amount":3,"unitName":"g"}]}
            """));
        assertThat(food).isNull();
    }
    @Test void checksImageSignaturesNotOnlyBrowserContentTypes() {
        assertThat(WellnessAiDraftService.detect(new byte[]{(byte)255,(byte)216,(byte)255,0,0,0,0,0,0,0,0,0}))
            .isEqualTo("image/jpeg");
        assertThat(WellnessAiDraftService.detect(new byte[]{1,2,3,4,5,6,7,8,9,10,11,12})).isNull();
    }
}
