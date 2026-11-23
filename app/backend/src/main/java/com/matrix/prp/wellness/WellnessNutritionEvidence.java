package com.matrix.prp.wellness;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.wellness.WellnessModels.Meal;
import com.matrix.prp.wellness.WellnessModels.MealItem;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * H2-002: minimal, strictly structured evidence from a first-party confirmed
 * AI meal. Never persist the photo, image URL, source prompt, full OCR, raw model
 * response or arbitrary client properties.
 *
 * Existing wellness draft confirmation is transactional. This writer is called
 * in that transaction after the existing meal and item rows have been saved.
 */
final class WellnessNutritionEvidence {
    private static final Pattern SENSITIVE = Pattern.compile(
        "(?i)(?:1[3-9]\\d{9}|\\b\\d{8,}\\b|[\\w.+-]+@[\\w.-]+\\.[a-z]{2,}" +
        "|收货地址|收件人|联系电话|手机号|身份证|订单号|取件码|配送地址|" +
        "街道|门牌|楼栋|小区|单元号|微信号|支付账号)");
    private static final String REDACTED = "已隐藏敏感内容";

    private WellnessNutritionEvidence() {}

    /**
     * First interpretation is immutable across draft edits. Only food labels
     * and numerical weight candidates are retained; text/notes are excluded.
     */
    static Map<String,Object> initialSnapshot(Map<String,Object> verified,
                                              boolean imageProvided) {
        return initialSnapshot(verified, null, imageProvided);
    }

    /**
     * Optional model sourceContext is an untrusted suggestion. Copy only fields
     * strictly required for a food/order/label business record; never keep raw
     * OCR blocks, personal delivery data or model-provided macro totals as facts.
     */
    static Map<String,Object> initialSnapshot(Map<String,Object> verified,
                                              JsonNode modelContext,
                                              boolean imageProvided) {
        Map<String,Object> result = new LinkedHashMap<>();
        result.put("schemaVersion", 1);
        result.put("sourceType", imageProvided ? "IMAGE" : "TEXT");
        List<Map<String,Object>> items = new ArrayList<>();
        Object source = verified.get("items");
        if (source instanceof List<?> candidates) {
            for (Object value : candidates) {
                if (items.size() >= 30) break;
                if (!(value instanceof Map<?,?> candidate)) continue;
                String name = safeFoodName(candidate.get("name"));
                BigDecimal grams = safeDecimal(candidate.get("grams"));
                Map<String,Object> item = new LinkedHashMap<>();
                item.put("name", name);
                item.put("estimatedGrams", grams != null && grams.signum() > 0 ? grams : null);
                items.add(item);
            }
        }
        result.put("items", items);
        if (imageProvided && modelContext != null && modelContext.isObject()) {
            Map<String,Object> context=safeSourceContext(modelContext);
            if(!context.isEmpty())result.put("sourceContext",context);
        }
        return result;
    }

    static String safeFoodName(Object raw) {
        if (!(raw instanceof String name)) return REDACTED;
        String normalized = name.strip();
        if (normalized.isEmpty() || normalized.length() > 120 ||
            SENSITIVE.matcher(normalized).find() ||
            normalized.chars().anyMatch(c -> Character.isISOControl(c))) {
            return REDACTED;
        }
        return normalized;
    }

    static Map<String,Object> safeSourceContext(JsonNode node) {
        if (node == null || !node.isObject()) return Map.of();
        String kind = node.path("kind").asText("");
        if (!List.of("FOOD_PHOTO","ORDER_SCREENSHOT","NUTRITION_LABEL").contains(kind))
            return Map.of();

        Map<String,Object> context = new LinkedHashMap<>();
        context.put("kind",kind);
        if ("ORDER_SCREENSHOT".equals(kind)) {
            String merchant = safeBusinessText(node.path("merchantName").asText(""),100);
            if (merchant != null) context.put("merchantName",merchant);
        }
        JsonNode rows = node.path("lineItems");
        List<Map<String,Object>> sourceItems = new ArrayList<>();
        if (rows.isArray()) {
            for (JsonNode entry : rows) {
                if (sourceItems.size() >= 30) break;
                if (!entry.isObject()) continue;
                String name = safeFoodName(entry.path("name").asText(""));
                if (REDACTED.equals(name)) continue;
                Map<String,Object> clean = new LinkedHashMap<>();
                clean.put("name",name);
                if ("ORDER_SCREENSHOT".equals(kind)) {
                    BigDecimal purchased=positiveCandidate(entry.path("purchasedQuantity"),100);
                    if (purchased!=null) clean.put("purchasedQuantity",purchased);
                    String portion=safeBusinessText(entry.path("portionLabel").asText(""),50);
                    if (portion!=null)clean.put("portionLabel",portion);
                }
                if ("NUTRITION_LABEL".equals(kind)) {
                    BigDecimal grams=positiveCandidate(entry.path("packageGrams"),10000);
                    if (grams!=null)clean.put("packageGrams",grams);
                    JsonNode label=entry.path("labelPer100g");
                    if (!label.isObject()) label=entry.path("labelPer100gCandidate");
                    if (label.isObject()) {
                        Map<String,Object> nutrition = new LinkedHashMap<>();
                        for (String field : List.of("caloriesKcal","proteinG","carbsG",
                                "fatG","sugarG","fiberG","sodiumMg")) {
                            int limit="caloriesKcal".equals(field)?900:
                                "sodiumMg".equals(field)?50000:100;
                            BigDecimal number=boundedCandidate(label.path(field),limit);
                            if(number!=null)nutrition.put(field,number);
                        }
                        if(!nutrition.isEmpty()){
                            clean.put("labelPer100gCandidate",nutrition);
                            clean.put("labelVerified",false);
                        }
                    }
                }
                sourceItems.add(clean);
            }
        }
        if (!sourceItems.isEmpty()) context.put("lineItems",sourceItems);
        // No user/OCR text fields ever flow to persistence.
        return context;
    }

    private static String safeBusinessText(String input,int maxLength){
        String value=input.strip();
        if(value.isEmpty() || value.length()>maxLength || SENSITIVE.matcher(value).find()
                || value.chars().anyMatch(Character::isISOControl)) return null;
        return value;
    }

    private static BigDecimal boundedCandidate(JsonNode node,int max){
        if(!node.isNumber())return null;
        BigDecimal n=safeDecimal(node.decimalValue());
        return n!=null && n.compareTo(BigDecimal.valueOf(max))<=0?n:null;
    }
    private static BigDecimal positiveCandidate(JsonNode node,int max){
        BigDecimal n=boundedCandidate(node,max);
        return n!=null && n.signum()>0?n:null;
    }

    private static BigDecimal safeDecimal(Object value) {
        try {
            if (value == null || value instanceof Boolean) return null;
            BigDecimal number = new BigDecimal(value.toString());
            return number.signum() >= 0 && number.compareTo(new BigDecimal("20000")) <= 0
                && number.scale() <= 4 ? number : null;
        } catch (NumberFormatException ex) {
            return null;
        }
    }

    /**
     * Only the server-generated initial extraction is eligible. Client-supplied
     * `rawExtraction` / `analysis` are not copied into the saved evidence.
     */
    static void saveConfirmed(JdbcTemplate db, ObjectMapper json, Meal meal,
                              JsonNode immutableInitial, String modelKey) {
        if (immutableInitial == null || !immutableInitial.isObject() ||
            immutableInitial.path("schemaVersion").asInt(-1) != 1 ||
            !immutableInitial.path("items").isArray() ||
            immutableInitial.path("items").size() > 30) {
            return; // Old drafts remain fully backwards-compatible.
        }
        String kind = immutableInitial.path("sourceType").asText("");
        if (!"TEXT".equals(kind) && !"IMAGE".equals(kind)) return;
        if (meal == null || meal.id() <= 0 || meal.items() == null) {
            throw new IllegalStateException("A confirmed meal is required");
        }

        Map<String,Object> sanitizedInitial = new LinkedHashMap<>();
        sanitizedInitial.put("schemaVersion", 1);
        sanitizedInitial.put("sourceType", kind);
        List<Map<String,Object>> initialItems = new ArrayList<>();
        for (JsonNode candidate : immutableInitial.path("items")) {
            Map<String,Object> entry = new LinkedHashMap<>();
            entry.put("name", safeFoodName(candidate.path("name").asText("")));
            BigDecimal grams = candidate.hasNonNull("estimatedGrams")
                    ? safeDecimal(candidate.path("estimatedGrams").asText()) : null;
            entry.put("estimatedGrams", grams != null && grams.signum() > 0 ? grams : null);
            initialItems.add(entry);
        }
        sanitizedInitial.put("items", initialItems);
        if ("IMAGE".equals(kind) && immutableInitial.path("sourceContext").isObject()) {
            Map<String,Object> context=safeSourceContext(immutableInitial.path("sourceContext"));
            if(!context.isEmpty())sanitizedInitial.put("sourceContext",context);
        }

        Map<String,Object> analysis = new LinkedHashMap<>();
        analysis.put("schemaVersion", 1);
        analysis.put("confirmed", true);
        analysis.put("method", "CONFIRMED_MEAL_SNAPSHOT");
        List<Map<String,Object>> confirmedItems = new ArrayList<>();
        int knownProtein = 0, knownCarbs = 0, knownFat = 0;
        for (MealItem item : meal.items()) {
            if (item.id() <= 0) throw new IllegalStateException("Missing saved meal item ID");
            Map<String,Object> result = new LinkedHashMap<>();
            result.put("foodName", safeFoodName(item.foodName()));
            result.put("weightGrams", item.grams() != null && item.grams().signum() > 0
                    ? item.grams() : null);
            result.put("caloriesKcal", item.calories());
            result.put("proteinG", item.proteinG());
            result.put("carbsG", item.carbsG());
            result.put("fatG", item.fatG());
            result.put("source", item.foodId() > 0 ? "FOOD_CATALOG" : "USER_ESTIMATE");
            result.put("unknownWeight", item.grams() == null || item.grams().signum() == 0);
            confirmedItems.add(result);
            if (item.proteinG() != null) knownProtein++;
            if (item.carbsG() != null) knownCarbs++;
            if (item.fatG() != null) knownFat++;
        }
        analysis.put("items", confirmedItems);
        analysis.put("itemCount", confirmedItems.size());
        analysis.put("knownProteinItems", knownProtein);
        analysis.put("knownCarbsItems", knownCarbs);
        analysis.put("knownFatItems", knownFat);

        try {
            String raw = json.writeValueAsString(sanitizedInitial);
            String derived = json.writeValueAsString(analysis);
            if (raw.length() > 12000 || derived.length() > 20000)
                throw new IllegalArgumentException("Nutrition evidence exceeds size limit");
            String safeModel = modelKey == null ? null
                    : modelKey.substring(0, Math.min(100, modelKey.length()));
            db.update("INSERT INTO prp_wellness_meal_analyses " +
                    "(meal_id,version_number,source_type,raw_extraction_json,analysis_json,model_key) " +
                    "VALUES (?,1,?,?,?,?)",
                    meal.id(),kind,raw,derived,safeModel);
            for (MealItem item : meal.items()) {
                String source = item.foodId() > 0 ? "FOOD_CATALOG" : "USER_ESTIMATE";
                String confidence = item.foodId() > 0 ? "REFERENCE" : "UNVERIFIED";
                db.update("INSERT INTO prp_wellness_meal_item_nutrients " +
                    "(meal_item_id,protein_g,carbs_g,fat_g,source_type,confidence_level) " +
                    "VALUES (?,?,?,?,?,?)",
                    item.id(),item.proteinG(),item.carbsG(),item.fatG(),source,confidence);
            }
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("Nutrition evidence cannot be encoded", ex);
        }
    }
}
