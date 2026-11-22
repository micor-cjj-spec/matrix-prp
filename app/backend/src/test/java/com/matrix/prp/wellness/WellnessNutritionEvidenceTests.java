package com.matrix.prp.wellness;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.wellness.WellnessModels.Meal;
import com.matrix.prp.wellness.WellnessModels.MealItem;
import java.math.BigDecimal;
import java.sql.Timestamp;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class WellnessNutritionEvidenceTests {
    private final ObjectMapper json = new ObjectMapper();

    @AfterEach void clearIdentity() { SecurityContextHolder.clearContext(); }

    private void asOwner(long id) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(
                new UserProfile(id, "ci_owner", "CI Owner"), null, List.of()));
    }

    @Test void originalSnapshotIsSmallStructuredAndRedactsPrivateOrderFields() throws Exception {
        Map<String,Object> source = new LinkedHashMap<>();
        source.put("items", List.of(
            Map.of("name", "红油抄手", "grams", new BigDecimal("220"),
                   "customerPhone", "13800138000", "imageBase64", "VERY_SECRET_IMAGE"),
            Map.of("name", "外卖收货地址XX街道", "grams", BigDecimal.ZERO)));
        source.put("originalPrompt", "收货人李某 13800138000");
        source.put("rawOcrText", "订单号123456789012");
        var extracted = WellnessNutritionEvidence.initialSnapshot(source, true);
        var saved = json.writeValueAsString(extracted);
        assertThat(saved).contains("红油抄手", "IMAGE", "220");
        assertThat(saved).contains("已隐藏敏感内容");
        assertThat(saved).doesNotContain("VERY_SECRET_IMAGE", "13800138000", "订单号",
                                        "收货地址XX", "originalPrompt", "rawOcrText");
    }

    @Test void confirmedEvidenceStoresOnlyKnownNutrientsAndNotFakeWeight() throws Exception {
        var source = Map.<String,Object>of("items",
            List.of(Map.of("name","水饺","grams",BigDecimal.ZERO)));
        var extraction = json.valueToTree(
            WellnessNutritionEvidence.initialSnapshot(source, true));
        var meal = new Meal(35L, LocalDate.of(2026,11,13), "LUNCH", null,
            List.of(
                new MealItem(41L, 0L, "水饺", BigDecimal.ZERO,
                    new BigDecimal("460"), null, null, null, true),
                new MealItem(42L, 17L, "鸡蛋", new BigDecimal("50"),
                    new BigDecimal("72"), new BigDecimal("6.5"),
                    new BigDecimal("0.3"), new BigDecimal("4.4"), true)
            ));
        JdbcTemplate db = mock(JdbcTemplate.class);
        WellnessNutritionEvidence.saveConfirmed(db, json, meal, extraction, "model-name");

        var initial = org.mockito.ArgumentCaptor.forClass(String.class);
        var analysis = org.mockito.ArgumentCaptor.forClass(String.class);
        verify(db).update(startsWith("INSERT INTO prp_wellness_meal_analyses"),
            eq(35L), eq("IMAGE"), initial.capture(), analysis.capture(), eq("model-name"));
        assertThat(initial.getValue()).doesNotContain("base64", "rawOcr", "modelOutput");
        var parsed = json.readTree(analysis.getValue());
        assertThat(parsed.path("confirmed").asBoolean()).isTrue();
        assertThat(parsed.path("items").get(0).path("weightGrams").isNull()).isTrue();
        assertThat(parsed.path("items").get(0).path("proteinG").isNull()).isTrue();
        assertThat(parsed.path("items").get(1).path("proteinG").decimalValue())
            .isEqualByComparingTo("6.5");
        assertThat(parsed.path("knownProteinItems").asInt()).isEqualTo(1);
        verify(db,times(2)).update(startsWith("INSERT INTO prp_wellness_meal_item_nutrients"),
            any(Object[].class));
    }

    @Test void oldDraftWithoutInitialExtractionDoesNotWriteEnrichment() {
        JdbcTemplate db = mock(JdbcTemplate.class);
        WellnessNutritionEvidence.saveConfirmed(db, json, null, json.createObjectNode(), "old-model");
        verifyNoInteractions(db);
    }

    @Test void editedDraftCannotReplaceServerCapturedInitialExtraction() throws Exception {
        asOwner(71L);
        var draftId = "12345678-1234-1234-1234-123456789012";
        var original = Map.<String,Object>of("schemaVersion", 1, "sourceType", "IMAGE",
            "items", List.of(Map.of("name", "米饭", "estimatedGrams", 150)));
        String oldPayload = json.writeValueAsString(Map.of(
            "_initialExtraction", original, "date", LocalDate.now(ZoneId.of("Asia/Shanghai")).toString(),
            "mealType", "LUNCH", "items", List.of()));
        JdbcTemplate db = mock(JdbcTemplate.class);
        var wellness = mock(WellnessService.class);
        when(wellness.profile()).thenReturn(
            new com.matrix.prp.wellness.WellnessModels.Profile(null, "Asia/Shanghai"));
        var service = new WellnessAiDraftService(db, wellness, mock(com.matrix.prp.ai.AiSettingsService.class),
            mock(com.matrix.prp.ai.AiStore.class),json,20,20,1000,1000);
        when(db.queryForList(contains("FROM prp_wellness_ai_drafts"),
                eq(draftId),eq(71L))).thenReturn(List.of(Map.of(
            "action_type", "meal.create", "status", "PENDING",
            "expires_at", Timestamp.valueOf(LocalDateTime.now().plusMinutes(10)),
            "model_used", "ci/test", "payload_json", oldPayload)));
        when(db.update(anyString(),any(Object[].class))).thenReturn(1);
        String day = LocalDate.now(ZoneId.of("Asia/Shanghai")).toString();
        var malicious = json.readTree("""
            {"date":"%s","mealType":"LUNCH",
             "items":[{"mode":"manual","name":"鸡蛋","foodId":0,"grams":0,"manualCalories":120}],
             "_initialExtraction":{"schemaVersion":1,"items":[{"name":"FORGED"}]}}
            """.formatted(day));
        var view = service.edit(draftId, malicious);
        var carried = json.valueToTree(view.values()).path("_initialExtraction");
        assertThat(carried.path("items").get(0).path("name").asText()).isEqualTo("米饭");
        assertThat(carried.toString()).doesNotContain("FORGED");
    }

    @Test void confirmingFirstPartyDraftWritesEvidenceBeforeDraftIsConsumed() throws Exception {
        asOwner(71L);
        JdbcTemplate db = mock(JdbcTemplate.class);
        var wellness = mock(WellnessService.class);
        when(wellness.profile()).thenReturn(
            new com.matrix.prp.wellness.WellnessModels.Profile(null, "Asia/Shanghai"));
        var service = new WellnessAiDraftService(db, wellness,
            mock(com.matrix.prp.ai.AiSettingsService.class),
            mock(com.matrix.prp.ai.AiStore.class),json,20,20,1000,1000);
        String draftId = "22345678-1234-1234-1234-123456789012";
        String day = LocalDate.now(ZoneId.of("Asia/Shanghai")).toString();
        var initial = Map.<String,Object>of("schemaVersion",1,"sourceType","IMAGE",
            "items",List.of(Map.of("name","红油馄饨","estimatedGrams",0)));
        var payload = Map.<String,Object>of(
            "date",day,"mealType","LUNCH","note","人工审核",
            "items",List.of(Map.of("foodId",0,"mode","manual","name","红油馄饨",
                "grams",0,"manualCalories",470)),
            "_initialExtraction",initial);
        when(db.queryForList(contains("FROM prp_wellness_ai_drafts"),
            eq(draftId),eq(71L))).thenReturn(List.of(Map.of(
                "action_type","meal.create","status","PENDING",
                "expires_at",Timestamp.valueOf(LocalDateTime.now().plusMinutes(10)),
                "payload_json",json.writeValueAsString(payload),"model_used","ci/vision")));
        when(db.update(anyString(),any(Object[].class))).thenReturn(1);
        var stored = new Meal(71L, LocalDate.parse(day), "LUNCH", null,
            List.of(new MealItem(171L,0L,"红油馄饨",BigDecimal.ZERO,
                new BigDecimal("470"),null,null,null,true)));
        when(wellness.addAiMeal(any(),anyString(),anyString(),anyList(),eq(draftId)))
            .thenReturn(stored);

        var result = service.confirm(draftId);
        assertThat(result.saved()).isEqualTo(stored);
        var order = inOrder(db);
        order.verify(db).update(startsWith("INSERT INTO prp_wellness_meal_analyses"),
            any(Object[].class));
        order.verify(db).update(startsWith("INSERT INTO prp_wellness_meal_item_nutrients"),
            any(Object[].class));
        order.verify(db).update(contains("status='CONSUMED'"),eq(draftId),eq(71L));
        verify(db).update(startsWith("INSERT INTO prp_wellness_meal_analyses"),
            eq(71L),eq("IMAGE"),anyString(),anyString(),eq("ci/vision"));
        verify(db,never()).update(contains("prp_wellness_foods"),any(Object[].class));
    }

    @Test void deliveryScreenshotPreservesPurchasedQuantityWithoutPersonalOrderData() throws Exception {
        var context = json.readTree("""
            {
              "kind":"ORDER_SCREENSHOT",
              "merchantName":"好味水饺",
              "lineItems":[{
                 "name":"鲜肉水饺",
                 "purchasedQuantity":2,
                 "portionLabel":"18个/份",
                 "deliveryAddress":"某省某市XX路",
                 "phone":"13800138000",
                 "orderNo":"AB123456789012",
                 "price":35.8
              }],
              "originalOcr":"张某 13800138000 某市某区"
            }
            """);
        Map<String,Object> verified = Map.of("items",List.of(Map.of(
            "name","鲜肉水饺","grams",BigDecimal.ZERO)));
        var snap=WellnessNutritionEvidence.initialSnapshot(verified,context,true);
        var raw=json.writeValueAsString(snap);
        assertThat(raw).contains("ORDER_SCREENSHOT","好味水饺","鲜肉水饺",
            "purchasedQuantity","2","18个/份");
        assertThat(raw).doesNotContain("deliveryAddress","phone","13800138000",
            "orderNo","AB123456789012","originalOcr","某市某区","price");
        assertThat(json.valueToTree(snap).path("sourceContext").path("lineItems")
            .get(0).path("purchasedQuantity").intValue()).isEqualTo(2);
        // The image is not the user's meal confirmation: purchasedQuantity
        // never creates a confirmed gram/serving count automatically.
        assertThat(json.valueToTree(snap).path("items").get(0)
            .path("estimatedGrams").isNull()).isTrue();
    }

    @Test void nutritionLabelIsUnverifiedCandidateNotConfirmedNutrition() throws Exception {
        var model = json.readTree("""
            {"kind":"NUTRITION_LABEL","lineItems":[{
               "name":"低脂牛奶",
               "packageGrams":250,
               "labelPer100g":{"caloriesKcal":55,"proteinG":3.2,
                   "carbsG":5,"fatG":1.2,"sodiumMg":60,
                   "fakeMetric":9876},
               "rawOcrText":"13800138000 路口"
            }],"imageBase64":"LEAK"}
            """);
        var snap=WellnessNutritionEvidence.initialSnapshot(
            Map.of("items",List.of(Map.of("name","低脂牛奶","grams",0))),
            model,true);
        var safe=json.writeValueAsString(snap);
        assertThat(safe).contains("NUTRITION_LABEL","labelPer100gCandidate",
            "packageGrams","labelVerified");
        assertThat(safe).doesNotContain("LEAK","fakeMetric","rawOcrText","路口");
        var sourceLabel=json.valueToTree(snap).path("sourceContext")
            .path("lineItems").get(0);
        assertThat(sourceLabel.path("labelVerified").asBoolean(true)).isFalse();
        assertThat(sourceLabel.path("labelPer100gCandidate")
            .path("proteinG").decimalValue()).isEqualByComparingTo("3.2");

        JdbcTemplate db=mock(JdbcTemplate.class);
        var meal=new Meal(105L, LocalDate.of(2026,11,13), "BREAKFAST", null,
            List.of(new MealItem(106L,0L,"低脂牛奶",BigDecimal.ZERO,
                new BigDecimal("130"),null,null,null,true)));
        WellnessNutritionEvidence.saveConfirmed(db,json,meal,json.valueToTree(snap),"ci/vision");
        var rawCaptor=org.mockito.ArgumentCaptor.forClass(String.class);
        var derivedCaptor=org.mockito.ArgumentCaptor.forClass(String.class);
        verify(db).update(startsWith("INSERT INTO prp_wellness_meal_analyses"),
            eq(105L),eq("IMAGE"),rawCaptor.capture(),derivedCaptor.capture(),eq("ci/vision"));
        assertThat(json.readTree(rawCaptor.getValue()).path("sourceContext")
            .path("lineItems").get(0).path("labelPer100gCandidate")
            .path("proteinG").decimalValue()).isEqualByComparingTo("3.2");
        assertThat(json.readTree(derivedCaptor.getValue()).path("items")
            .get(0).path("proteinG").isNull()).isTrue();
    }

    @Test void oversizeOrSensitiveModelBusinessFieldsAreDiscarded() throws Exception {
        var model=json.readTree("""
            {"kind":"ORDER_SCREENSHOT","merchantName":"李某的配送地址某街道",
             "lineItems":[
               {"name":"米饭","purchasedQuantity":2,"portionLabel":"13800138000"},
               {"name":"手机号13800138000","purchasedQuantity":99999}
             ]}
            """);
        var snap=WellnessNutritionEvidence.initialSnapshot(
            Map.of("items",List.of(Map.of("name","米饭","grams",0))),model,true);
        var source=json.valueToTree(snap).path("sourceContext");
        assertThat(source.has("merchantName")).isFalse();
        assertThat(source.path("lineItems").size()).isEqualTo(1);
        assertThat(source.path("lineItems").get(0).has("portionLabel")).isFalse();
        assertThat(source.path("lineItems").get(0).path("purchasedQuantity").asInt())
            .isEqualTo(2);
    }

    @Test void purchasedTwoPortionsOnlyOneConfirmedPortionCountsInNutrition() throws Exception {
        var model=json.readTree("""
            {"kind":"ORDER_SCREENSHOT","merchantName":"张记水饺",
              "lineItems":[{"name":"水饺","purchasedQuantity":2,"portionLabel":"18个/份"}]}
            """);
        var extracted=json.valueToTree(WellnessNutritionEvidence.initialSnapshot(
            Map.of("items",List.of(Map.of("name","水饺","grams",BigDecimal.ZERO))),
            model,true));
        JdbcTemplate db=mock(JdbcTemplate.class);
        // User confirmed eating ONE serving. Actual snapshot is authoritative.
        var confirmed=new Meal(301L,LocalDate.of(2026,11,13),"LUNCH",null,
            List.of(new MealItem(302L,0L,"水饺",BigDecimal.ZERO,
                new BigDecimal("350"),null,null,null,true)));
        WellnessNutritionEvidence.saveConfirmed(db,json,confirmed,extracted,"ci/model");
        var raw=org.mockito.ArgumentCaptor.forClass(String.class);
        var analysis=org.mockito.ArgumentCaptor.forClass(String.class);
        verify(db).update(startsWith("INSERT INTO prp_wellness_meal_analyses"),
            eq(301L),eq("IMAGE"),raw.capture(),analysis.capture(),eq("ci/model"));
        assertThat(json.readTree(raw.getValue()).path("sourceContext").path("lineItems")
                .get(0).path("purchasedQuantity").asInt()).isEqualTo(2);
        var finalItems=json.readTree(analysis.getValue()).path("items");
        assertThat(finalItems.size()).isEqualTo(1);
        assertThat(finalItems.get(0).path("caloriesKcal").decimalValue())
            .isEqualByComparingTo("350");
        assertThat(analysis.getValue()).doesNotContain("purchasedQuantity","18个/份");
        verify(db,times(1)).update(startsWith("INSERT INTO prp_wellness_meal_item_nutrients"),
            any(Object[].class));
    }
}
