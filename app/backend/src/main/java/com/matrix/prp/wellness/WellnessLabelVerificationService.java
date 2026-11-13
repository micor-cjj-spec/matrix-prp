package com.matrix.prp.wellness;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.common.api.ResourceNotFoundException;
import com.matrix.prp.wellness.WellnessModels.Meal;
import com.matrix.prp.wellness.WellnessModels.MealItem;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/**
 * H2: explicit owner verification of a single per-100g package label.
 * Original model evidence remains immutable. No photo or full OCR is saved.
 * Never treat a model-proposed nutrition label as confirmed by default.
 */
@Service
@Profile("!test")
public class WellnessLabelVerificationService {
    public record LabelInput(long mealItemId, BigDecimal consumedGrams,
                             BigDecimal caloriesPer100g, BigDecimal proteinPer100g,
                             BigDecimal carbsPer100g, BigDecimal fatPer100g,
                             BigDecimal fiberPer100g, BigDecimal sugarPer100g,
                             BigDecimal sodiumMgPer100g, Boolean userVerified) {}

    private final JdbcTemplate db;
    private final WellnessService wellness;
    private final WellnessNutritionDetailsService details;
    private final ObjectMapper json;

    public WellnessLabelVerificationService(JdbcTemplate db, WellnessService wellness,
            WellnessNutritionDetailsService details, ObjectMapper json) {
        this.db=db;this.wellness=wellness;this.details=details;this.json=json;
    }

    private static ResponseStatusException invalid(String field) {
        return new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY,
                "包装营养标签需人工核对：" + field);
    }

    private static BigDecimal check(BigDecimal number, String field,
                                    BigDecimal maximum, boolean positive) {
        if (number==null || number.signum() < (positive?1:0) ||
            number.compareTo(maximum)>0 || number.scale()>3) throw invalid(field);
        return number;
    }

    private static BigDecimal optional(BigDecimal number, String field, BigDecimal max) {
        return number==null?null:check(number,field,max,false);
    }

    private static BigDecimal consumed(BigDecimal per100g,BigDecimal grams) {
        return per100g==null?null:NutritionMath.portion(per100g,grams);
    }

    /** Jackson can decode JSON 54 as an integer even when input used BigDecimal. */
    private static boolean sameUserInput(JsonNode previous,Map<String,Object> expected) {
        if(!previous.isObject())return false;
        for(var entry:expected.entrySet()) {
            JsonNode value=previous.path(entry.getKey());
            Object expectedValue=entry.getValue();
            if(expectedValue==null) {
                if(!value.isNull())return false;
            } else if(expectedValue instanceof BigDecimal decimal) {
                if(!value.isNumber() || value.decimalValue().compareTo(decimal)!=0)return false;
            } else if(expectedValue instanceof Number numeric) {
                if(!value.isNumber() || value.longValue()!=numeric.longValue())return false;
            } else if(expectedValue instanceof Boolean checked) {
                if(!value.isBoolean() || value.booleanValue()!=checked)return false;
            } else {
                return false;
            }
        }
        return true;
    }

    private static JsonNode decode(ObjectMapper json,String raw) {
        try { return json.readTree(raw); }
        catch (Exception ex) { throw new IllegalStateException("Invalid persisted label evidence",ex); }
    }

    @Transactional
    public WellnessNutritionDetailsService.MealDetails confirm(long mealId,LabelInput input) {
        long owner=CurrentUser.id();
        if(mealId<=0 || input==null || input.mealItemId()<=0)
            throw invalid("餐食及食物条目");
        if(!Boolean.TRUE.equals(input.userVerified()))
            throw invalid("请先核对包装上每100g营养值及实际食用克数");
        BigDecimal grams=check(input.consumedGrams(),"实际食用克数",new BigDecimal("3000"),true);
        if(grams.compareTo(new BigDecimal("0.1"))<0 || grams.scale()>2)
            throw invalid("实际食用克数");
        BigDecimal kcal100=check(input.caloriesPer100g(),"每100g热量",new BigDecimal("900"),true);
        BigDecimal protein100=check(input.proteinPer100g(),"每100g蛋白质",new BigDecimal("100"),false);
        BigDecimal carbs100=check(input.carbsPer100g(),"每100g碳水",new BigDecimal("100"),false);
        BigDecimal fat100=check(input.fatPer100g(),"每100g脂肪",new BigDecimal("100"),false);
        if(protein100.add(carbs100).add(fat100).compareTo(new BigDecimal("110"))>0)
            throw invalid("每100g三大营养素总量");
        BigDecimal fiber100=optional(input.fiberPer100g(),"每100g膳食纤维",new BigDecimal("100"));
        BigDecimal sugar100=optional(input.sugarPer100g(),"每100g糖",new BigDecimal("100"));
        BigDecimal sodium100=optional(input.sodiumMgPer100g(),"每100g钠",new BigDecimal("50000"));
        if(sugar100!=null && sugar100.compareTo(carbs100)>0)
            throw invalid("糖含量不能大于碳水总量");
        // SQL row lock ensures version progression and exactly-one app update.
        List<Map<String,Object>> locks=db.queryForList(
            "SELECT id FROM prp_wellness_meals WHERE id=? AND user_id=? FOR UPDATE",
            mealId,owner);
        if(locks.isEmpty())throw new ResourceNotFoundException("Meal not found");
        Meal meal=wellness.ownedMeal(mealId);
        MealItem item=meal.items().stream().filter(i->i.id()==input.mealItemId())
            .findFirst().orElseThrow(()->new ResourceNotFoundException("Meal item not found"));
        if(item.foodId()>0)
            throw invalid("食品库条目请使用食品库营养值，包装核验仅支持单品手动记录");

        List<Map<String,Object>> versions=db.queryForList(
            "SELECT version_number,raw_extraction_json,analysis_json " +
            "FROM prp_wellness_meal_analyses WHERE meal_id=? ORDER BY version_number ASC",
            mealId);
        if(versions.isEmpty())throw invalid("缺少原始包装标签识别凭据");
        String raw=String.valueOf(versions.getFirst().get("raw_extraction_json"));
        JsonNode first=decode(json,raw);
        JsonNode context=first.path("sourceContext");
        if(!"NUTRITION_LABEL".equals(context.path("kind").asText()))
            throw invalid("来源不是包装营养标签");
        JsonNode lines=context.path("lineItems");
        int matched=0;
        if(lines.isArray())for(JsonNode line:lines) {
            if(line.path("labelPer100gCandidate").isObject()
               && line.path("name").asText().strip().equals(item.foodName())) matched++;
        }
        if(matched!=1)throw invalid("未找到唯一对应的包装标签食物，请核对名称");

        Map<String,Object> normalized=new LinkedHashMap<>();
        normalized.put("mealItemId",item.id());
        normalized.put("consumedGrams",grams);
        normalized.put("caloriesPer100g",kcal100);
        normalized.put("proteinPer100g",protein100);
        normalized.put("carbsPer100g",carbs100);
        normalized.put("fatPer100g",fat100);
        normalized.put("fiberPer100g",fiber100);
        normalized.put("sugarPer100g",sugar100);
        normalized.put("sodiumMgPer100g",sodium100);
        normalized.put("userVerified",true);
        Map<String,Object> mostRecent=versions.getLast();
        JsonNode previous=decode(json,String.valueOf(mostRecent.get("analysis_json")));
        if("USER_VERIFIED_LABEL".equals(previous.path("method").asText())
                && sameUserInput(previous.path("userInput"),normalized)) {
            return details.readOwnedMeal(mealId); // Identical request is idempotent.
        }

        BigDecimal kcal=consumed(kcal100,grams);
        BigDecimal protein=consumed(protein100,grams);
        BigDecimal carbs=consumed(carbs100,grams);
        BigDecimal fat=consumed(fat100,grams);
        BigDecimal fiber=consumed(fiber100,grams);
        BigDecimal sugar=consumed(sugar100,grams);
        BigDecimal sodium=consumed(sodium100,grams);
        int saved=db.update(
            "UPDATE prp_wellness_meal_items SET grams=?,calories=?,protein_g=?,carbs_g=?,fat_g=? " +
            "WHERE id=? AND meal_id=?",
            grams,kcal,protein,carbs,fat,item.id(),mealId);
        if(saved!=1)throw new IllegalStateException("Confirmed meal item changed");
        int enriched=db.update(
            "UPDATE prp_wellness_meal_item_nutrients SET quantity=?,quantity_unit='g'," +
            "weight_min_g=?,weight_max_g=?,calories_min_kcal=?,calories_max_kcal=?," +
            "protein_g=?,carbs_g=?,fat_g=?,fiber_g=?,sugar_g=?,sodium_mg=?," +
            "source_type='USER_LABEL',confidence_level='USER_VERIFIED',estimate_note=? " +
            "WHERE meal_item_id=?",
            grams,grams,grams,kcal,kcal,protein,carbs,fat,fiber,sugar,sodium,
            "用户核对包装每100g数值并输入实际食用克数",item.id());
        if(enriched!=1)throw new IllegalStateException("Missing V30 item enrichment row");
        Map<String,Object> analysis=new LinkedHashMap<>();
        analysis.put("schemaVersion",1);
        analysis.put("method","USER_VERIFIED_LABEL");
        analysis.put("userInput",normalized);
        analysis.put("calculated",Map.of("caloriesKcal",kcal,"proteinG",protein,
            "carbsG",carbs,"fatG",fat));
        Map<String,Object> optionalTotals=new LinkedHashMap<>();
        optionalTotals.put("fiberG",fiber);
        optionalTotals.put("sugarG",sugar);
        optionalTotals.put("sodiumMg",sodium);
        analysis.put("additionalNutrients",optionalTotals);
        int last=((Number)mostRecent.get("version_number")).intValue();
        if(last>=20)throw invalid("分析历史达到版本上限");
        try {
            db.update("INSERT INTO prp_wellness_meal_analyses " +
                "(meal_id,version_number,source_type,raw_extraction_json,analysis_json,model_key) " +
                "VALUES (?,?,?,?,?,?)",
                mealId,last+1,"IMAGE",raw,json.writeValueAsString(analysis),"user/verified-label");
        } catch(com.fasterxml.jackson.core.JsonProcessingException ex) {
            throw new IllegalStateException("Unable to save verified nutrition label",ex);
        }
        return details.readOwnedMeal(mealId);
    }
}
