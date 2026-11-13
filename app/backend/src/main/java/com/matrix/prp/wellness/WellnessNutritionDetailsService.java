package com.matrix.prp.wellness;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.wellness.WellnessModels.Meal;
import com.matrix.prp.wellness.WellnessModels.MealItem;
import java.math.BigDecimal;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.util.List;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

/**
 * Read-only H2-002 projection for confirmed meals.
 *
 * Historical meals without V30 enrichment return empty detail arrays; missing
 * nutrients are never silently coerced to zero. Pictures and image references
 * are not part of this contract.
 */
@Service
@Profile("!test")
public class WellnessNutritionDetailsService {
    public record Analysis(long id, int versionNumber, String sourceType,
                           JsonNode rawExtraction, JsonNode analysis,
                           String modelKey, Instant createdAt) {}

    public record ItemNutrients(long mealItemId, String foodName,
                                BigDecimal quantity, String quantityUnit,
                                BigDecimal consumedRatio, BigDecimal weightMinG,
                                BigDecimal weightMaxG, BigDecimal caloriesMinKcal,
                                BigDecimal caloriesMaxKcal, BigDecimal proteinG,
                                BigDecimal carbsG, BigDecimal fatG,
                                BigDecimal fiberG, BigDecimal sugarG,
                                BigDecimal sodiumMg, String sourceType,
                                String confidenceLevel, String estimateNote) {}

    public record NutritionCompleteness(int foodCount, int knownProteinCount,
                                       int knownCarbsCount, int knownFatCount) {}

    public record MealDetails(Meal meal, List<Analysis> analyses,
                              List<ItemNutrients> nutrients,
                              NutritionCompleteness nutritionCompleteness) {}

    private final JdbcTemplate db;
    private final WellnessService wellness;
    private final ObjectMapper json;

    public WellnessNutritionDetailsService(JdbcTemplate db,
                                           WellnessService wellness,
                                           ObjectMapper json) {
        this.db = db;
        this.wellness = wellness;
        this.json = json;
    }

    private JsonNode parsedJson(String raw) {
        try {
            return json.readTree(raw);
        } catch (Exception ex) {
            // A malformed persisted analysis is a storage error, not a cue to
            // fabricate an empty object or to reinterpret nutritional values.
            throw new IllegalStateException("Invalid persisted nutrition analysis", ex);
        }
    }

    private Analysis mapAnalysis(ResultSet r, int row) throws SQLException {
        return new Analysis(r.getLong("id"), r.getInt("version_number"),
                r.getString("source_type"),
                parsedJson(r.getString("raw_extraction_json")),
                parsedJson(r.getString("analysis_json")),
                r.getString("model_key"),
                r.getTimestamp("created_at").toInstant());
    }

    private ItemNutrients mapNutrients(ResultSet r, int row) throws SQLException {
        return new ItemNutrients(
                r.getLong("meal_item_id"), r.getString("food_name"),
                r.getBigDecimal("quantity"), r.getString("quantity_unit"),
                r.getBigDecimal("consumed_ratio"),
                r.getBigDecimal("weight_min_g"), r.getBigDecimal("weight_max_g"),
                r.getBigDecimal("calories_min_kcal"), r.getBigDecimal("calories_max_kcal"),
                r.getBigDecimal("protein_g"), r.getBigDecimal("carbs_g"),
                r.getBigDecimal("fat_g"), r.getBigDecimal("fiber_g"),
                r.getBigDecimal("sugar_g"), r.getBigDecimal("sodium_mg"),
                r.getString("source_type"), r.getString("confidence_level"),
                r.getString("estimate_note"));
    }

    public MealDetails readOwnedMeal(long mealId) {
        if (mealId <= 0) throw new IllegalArgumentException("Positive meal ID required");
        // Existing service is the authoritative owner-scoped lookup.
        Meal meal = wellness.ownedMeal(mealId);
        long owner = CurrentUser.id();

        List<Analysis> analyses = db.query(
                "SELECT a.id,a.version_number,a.source_type,a.raw_extraction_json," +
                "a.analysis_json,a.model_key,a.created_at " +
                "FROM prp_wellness_meal_analyses a " +
                "JOIN prp_wellness_meals m ON m.id=a.meal_id " +
                "WHERE m.id=? AND m.user_id=? ORDER BY a.version_number DESC LIMIT 20",
                this::mapAnalysis, mealId, owner);

        List<ItemNutrients> nutrients = db.query(
                "SELECT n.*,i.food_name FROM prp_wellness_meal_item_nutrients n " +
                "JOIN prp_wellness_meal_items i ON i.id=n.meal_item_id " +
                "JOIN prp_wellness_meals m ON m.id=i.meal_id " +
                "WHERE m.id=? AND m.user_id=? ORDER BY i.id",
                this::mapNutrients, mealId, owner);

        int protein = 0, carbs = 0, fat = 0;
        for (MealItem item : meal.items()) {
            if (item.proteinG() != null) protein++;
            if (item.carbsG() != null) carbs++;
            if (item.fatG() != null) fat++;
        }
        return new MealDetails(meal, analyses, nutrients,
                new NutritionCompleteness(meal.items().size(), protein, carbs, fat));
    }
}
