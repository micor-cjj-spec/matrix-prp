package com.matrix.prp.wellness;

import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.common.api.ResourceNotFoundException;
import com.matrix.prp.wellness.WellnessModels.*;
import java.math.BigDecimal;
import java.sql.PreparedStatement;
import java.sql.Statement;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@org.springframework.context.annotation.Profile("!test")
public class WellnessService {
    private final JdbcTemplate db;
    public WellnessService(JdbcTemplate db) { this.db = db; }

    private static final String FOOD_COLUMNS =
        "id,name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note,owner_user_id";
    private static final String ITEM_COLUMNS =
        "id,meal_id,food_id,food_name,grams,calories,protein_g,carbs_g,fat_g,is_estimate";

    private Food mapFood(java.sql.ResultSet r, int row) throws java.sql.SQLException {
        return new Food(r.getLong("id"), r.getString("name"), r.getString("preparation"),
                r.getBigDecimal("calories_100g"), r.getBigDecimal("protein_100g"),
                r.getBigDecimal("carbs_100g"), r.getBigDecimal("fat_100g"),
                r.getString("source_note"), r.getObject("owner_user_id") != null);
    }
    private MealItem mapItem(java.sql.ResultSet r, int row) throws java.sql.SQLException {
        return new MealItem(r.getLong("id"), r.getLong("food_id"), r.getString("food_name"),
                r.getBigDecimal("grams"), r.getBigDecimal("calories"), r.getBigDecimal("protein_g"),
                r.getBigDecimal("carbs_g"), r.getBigDecimal("fat_g"), r.getBoolean("is_estimate"));
    }
    private Exercise mapExercise(java.sql.ResultSet r, int row) throws java.sql.SQLException {
        return new Exercise(r.getLong("id"), r.getObject("performed_on", LocalDate.class),
                r.getString("name"), r.getInt("duration_minutes"), r.getBigDecimal("estimated_kcal"),
                r.getString("note"));
    }
    private BodyMetric mapMetric(java.sql.ResultSet r, int row) throws java.sql.SQLException {
        return new BodyMetric(r.getLong("id"), r.getObject("measured_on", LocalDate.class),
                r.getBigDecimal("weight_kg"), r.getBigDecimal("body_fat_pct"), r.getBigDecimal("waist_cm"));
    }
    private Goal mapGoal(java.sql.ResultSet r, int row) throws java.sql.SQLException {
        return new Goal(r.getLong("id"), r.getObject("effective_from", LocalDate.class),
                r.getBigDecimal("daily_calories"), r.getBigDecimal("daily_protein_g"),
                (Integer) r.getObject("weekly_activity_minutes"));
    }
    private long insert(String sql, Object... args) {
        KeyHolder keys = new GeneratedKeyHolder();
        db.update(connection -> {
            PreparedStatement statement = connection.prepareStatement(sql, Statement.RETURN_GENERATED_KEYS);
            for (int i=0; i<args.length; i++) statement.setObject(i+1, args[i]);
            return statement;
        }, keys);
        return Objects.requireNonNull(keys.getKey(), "Missing generated key").longValue();
    }
    public Profile profile() {
        List<Profile> rows=db.query("SELECT height_cm,timezone FROM prp_wellness_profiles WHERE user_id=?",
                (r,n)->new Profile(r.getBigDecimal("height_cm"),r.getString("timezone")),CurrentUser.id());
        return rows.isEmpty() ? new Profile(null,"Asia/Shanghai") : rows.get(0);
    }
    @Transactional
    public Profile saveProfile(ProfileInput input) {
        String tz=input.timezone().trim();
        if (tz.length()>64) throw new IllegalArgumentException("Timezone is too long");
        ZoneId.of(tz);
        db.update("INSERT INTO prp_wellness_profiles (user_id,height_cm,timezone) VALUES (?,?,?) " +
                "ON DUPLICATE KEY UPDATE height_cm=VALUES(height_cm),timezone=VALUES(timezone)",
                CurrentUser.id(),input.heightCm(),tz);
        return profile();
    }
    private LocalDate today() { return LocalDate.now(ZoneId.of(profile().timezone())); }

    public List<Food> foods(String q) {
        if(q!=null && q.length()>100) throw new IllegalArgumentException("Search is too long");
        String term=q==null?"":q.trim();
        return db.query("SELECT "+FOOD_COLUMNS+" FROM prp_wellness_foods " +
                "WHERE (owner_user_id IS NULL OR owner_user_id=?) AND name LIKE ? " +
                "ORDER BY CASE WHEN owner_user_id=? THEN 0 ELSE 1 END,name,id LIMIT 100",
                this::mapFood, CurrentUser.id(),"%"+term+"%", CurrentUser.id());
    }
    public List<Food> frequentFoods() {
        return db.query("SELECT "+FOOD_COLUMNS+" FROM prp_wellness_foods WHERE id IN (SELECT frequent.food_id FROM (" +
                "SELECT i.food_id FROM prp_wellness_meal_items i JOIN prp_wellness_meals m ON m.id=i.meal_id " +
                "WHERE m.user_id=? GROUP BY i.food_id ORDER BY COUNT(*) DESC LIMIT 12) frequent) " +
                "AND (owner_user_id IS NULL OR owner_user_id=?) ORDER BY name",
                this::mapFood,CurrentUser.id(),CurrentUser.id());
    }
    public Food addFood(FoodInput input) {
        String prep=input.preparation()==null?"unspecified":input.preparation().trim().toLowerCase(Locale.ROOT);
        if(!Set.of("raw","cooked","unspecified").contains(prep))
            throw new IllegalArgumentException("Invalid preparation");
        if(input.protein100g().add(input.fat100g()).add(input.carbs100g()).compareTo(new BigDecimal("110"))>0)
            throw new IllegalArgumentException("Food macros exceed 110g per 100g");
        long id=insert("INSERT INTO prp_wellness_foods " +
                "(owner_user_id,name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note) " +
                "VALUES (?,?,?,?,?,?,?,?)",
                CurrentUser.id(),input.name().trim(),prep,input.calories100g(),input.protein100g(),
                input.carbs100g(),input.fat100g(),input.sourceNote());
        return food(id);
    }
    /** Imported food remains owned by the requesting user; never mutates shared reference foods. */
    @Transactional
    public Food importUsda(UsdaFoodCatalog.Candidate candidate) {
        long user=CurrentUser.id();
        List<Food> existing=db.query("SELECT "+FOOD_COLUMNS+
            " FROM prp_wellness_foods WHERE owner_user_id=? AND source_note=? LIMIT 1",
            this::mapFood,user,candidate.source());
        if(!existing.isEmpty()) return existing.get(0);
        return addFood(new FoodInput(candidate.name(),"unspecified",candidate.calories100g(),
            candidate.protein100g(),candidate.carbs100g(),candidate.fat100g(),candidate.source()));
    }
    private Food food(long id) {
        List<Food> rows=db.query("SELECT "+FOOD_COLUMNS+" FROM prp_wellness_foods " +
                "WHERE id=? AND (owner_user_id IS NULL OR owner_user_id=?)",
                this::mapFood,id,CurrentUser.id());
        if(rows.isEmpty()) throw new ResourceNotFoundException("Food not found");
        return rows.get(0);
    }

    private void validateMeal(MealInput input) {
        if(!Set.of("BREAKFAST","LUNCH","DINNER","SNACK").contains(input.mealType()))
            throw new IllegalArgumentException("Invalid meal type");
        if(input.items().stream().anyMatch(i->i==null || i.foodId()==null || i.grams()==null))
            throw new IllegalArgumentException("Invalid meal item");
    }
    public List<Meal> meals(LocalDate date) {
        List<Meal> result=new ArrayList<>();
        db.query("SELECT id,meal_date,meal_type,note FROM prp_wellness_meals " +
                "WHERE user_id=? AND meal_date=? ORDER BY id DESC",r-> {
            result.add(mealFromRow(r));
        }, CurrentUser.id(),date);
        return result;
    }
    private Meal mealFromRow(java.sql.ResultSet r) throws java.sql.SQLException {
        long id=r.getLong("id");
        return new Meal(id,r.getObject("meal_date",LocalDate.class),r.getString("meal_type"),
                r.getString("note"),items(id));
    }
    private List<MealItem> items(long mealId) {
        return db.query("SELECT "+ITEM_COLUMNS+" FROM prp_wellness_meal_items WHERE meal_id=? ORDER BY id",
                this::mapItem,mealId);
    }
    private Meal meal(long id) {
        List<Meal> rows=db.query("SELECT id,meal_date,meal_type,note FROM prp_wellness_meals " +
                "WHERE id=? AND user_id=?", (r,n)->mealFromRow(r),id,CurrentUser.id());
        if(rows.isEmpty()) throw new ResourceNotFoundException("Meal not found");
        return rows.get(0);
    }
    @Transactional
    public Meal addMeal(MealInput input) {
        validateMeal(input);
        long user=CurrentUser.id();
        String key=input.idempotencyKey()==null || input.idempotencyKey().isBlank() ? null : input.idempotencyKey();
        if(key!=null) {
            List<Long> found=db.query("SELECT id FROM prp_wellness_meals WHERE user_id=? AND idempotency_key=?",
                    (r,n)->r.getLong("id"),user,key);
            if(!found.isEmpty()) return meal(found.get(0));
        }
        long id=insert("INSERT INTO prp_wellness_meals (user_id,meal_date,meal_type,note,idempotency_key) " +
                "VALUES (?,?,?,?,?)",user,input.mealDate(),input.mealType(),input.note(),key);
        insertItems(id,input.items());
        return meal(id);
    }
    @Transactional
    public Meal updateMeal(long id, MealInput input) {
        meal(id);validateMeal(input);
        db.update("UPDATE prp_wellness_meals SET meal_date=?,meal_type=?,note=? WHERE id=? AND user_id=?",
                input.mealDate(),input.mealType(),input.note(),id,CurrentUser.id());
        db.update("DELETE FROM prp_wellness_meal_items WHERE meal_id=?",id);
        insertItems(id,input.items());
        return meal(id);
    }
    private void insertItems(long id,List<ItemInput> inputs) {
        for(ItemInput item:inputs) {
            Food f=food(item.foodId());
            BigDecimal grams=item.grams();
            db.update("INSERT INTO prp_wellness_meal_items " +
                    "(meal_id,food_id,food_name,grams,calories,protein_g,carbs_g,fat_g,is_estimate) " +
                    "VALUES (?,?,?,?,?,?,?,?,?)",id,f.id(),f.name(),grams,
                    NutritionMath.portion(f.calories100g(),grams),
                    NutritionMath.portion(f.protein100g(),grams),
                    NutritionMath.portion(f.carbs100g(),grams),
                    NutritionMath.portion(f.fat100g(),grams),1);
        }
    }
    @Transactional
    public void deleteMeal(long id) {
        meal(id);
        db.update("DELETE FROM prp_wellness_meals WHERE id=? AND user_id=?",id,CurrentUser.id());
    }
    @Transactional
    public Meal copyMeal(long id,LocalDate date) {
        Meal existing=meal(id);
        List<ItemInput> copies=existing.items().stream().map(i->new ItemInput(i.foodId(),i.grams())).toList();
        return addMeal(new MealInput(date,existing.mealType(),existing.note(),copies,null));
    }

    public List<Exercise> exercises(LocalDate date) {
        return db.query("SELECT id,performed_on,name,duration_minutes,estimated_kcal,note FROM " +
                "prp_wellness_exercises WHERE user_id=? AND performed_on=? ORDER BY id DESC",
                this::mapExercise,CurrentUser.id(),date);
    }
    private Exercise exercise(long id) {
        List<Exercise> rows=db.query("SELECT id,performed_on,name,duration_minutes,estimated_kcal,note FROM " +
                "prp_wellness_exercises WHERE id=? AND user_id=?",this::mapExercise,id,CurrentUser.id());
        if(rows.isEmpty()) throw new ResourceNotFoundException("Exercise not found");
        return rows.get(0);
    }
    public Exercise addExercise(ExerciseInput input) {
        long id=insert("INSERT INTO prp_wellness_exercises " +
                "(user_id,performed_on,name,duration_minutes,estimated_kcal,note) VALUES (?,?,?,?,?,?)",
                CurrentUser.id(),input.performedOn(),input.name().trim(),input.durationMinutes(),
                input.estimatedKcal(),input.note());
        return exercise(id);
    }
    public Exercise updateExercise(long id,ExerciseInput input) {
        exercise(id);
        db.update("UPDATE prp_wellness_exercises SET performed_on=?,name=?,duration_minutes=?,estimated_kcal=?,note=? " +
                "WHERE id=? AND user_id=?",input.performedOn(),input.name().trim(),
                input.durationMinutes(),input.estimatedKcal(),input.note(),id,CurrentUser.id());
        return exercise(id);
    }
    public void deleteExercise(long id) {
        exercise(id);db.update("DELETE FROM prp_wellness_exercises WHERE id=? AND user_id=?",id,CurrentUser.id());
    }

    public List<BodyMetric> metrics(int days) {
        if(days<1||days>365) throw new IllegalArgumentException("days must be 1..365");
        return db.query("SELECT id,measured_on,weight_kg,body_fat_pct,waist_cm FROM prp_wellness_body_metrics " +
                "WHERE user_id=? AND measured_on>=? ORDER BY measured_on DESC,id DESC LIMIT 500",
                this::mapMetric,CurrentUser.id(),today().minusDays(days-1));
    }
    private BodyMetric metric(long id) {
        List<BodyMetric> rows=db.query("SELECT id,measured_on,weight_kg,body_fat_pct,waist_cm " +
                "FROM prp_wellness_body_metrics WHERE id=? AND user_id=?",this::mapMetric,id,CurrentUser.id());
        if(rows.isEmpty()) throw new ResourceNotFoundException("Body metric not found");
        return rows.get(0);
    }
    public BodyMetric addMetric(BodyMetricInput input) {
        long id=insert("INSERT INTO prp_wellness_body_metrics " +
                "(user_id,measured_on,weight_kg,body_fat_pct,waist_cm) VALUES (?,?,?,?,?)",
                CurrentUser.id(),input.measuredOn(),input.weightKg(),input.bodyFatPct(),input.waistCm());
        return metric(id);
    }
    public BodyMetric updateMetric(long id,BodyMetricInput input) {
        metric(id);
        db.update("UPDATE prp_wellness_body_metrics SET measured_on=?,weight_kg=?,body_fat_pct=?,waist_cm=? " +
                "WHERE id=? AND user_id=?",input.measuredOn(),input.weightKg(),
                input.bodyFatPct(),input.waistCm(),id,CurrentUser.id());
        return metric(id);
    }
    public void deleteMetric(long id) {
        metric(id);db.update("DELETE FROM prp_wellness_body_metrics WHERE id=? AND user_id=?",id,CurrentUser.id());
    }

    public List<Goal> goals() {
        return db.query("SELECT id,effective_from,daily_calories,daily_protein_g,weekly_activity_minutes " +
                "FROM prp_wellness_goals WHERE user_id=? ORDER BY effective_from DESC",this::mapGoal,CurrentUser.id());
    }
    @Transactional
    public Goal saveGoal(GoalInput input) {
        db.update("INSERT INTO prp_wellness_goals (user_id,effective_from,daily_calories,daily_protein_g,weekly_activity_minutes) " +
                "VALUES (?,?,?,?,?) ON DUPLICATE KEY UPDATE daily_calories=VALUES(daily_calories)," +
                "daily_protein_g=VALUES(daily_protein_g),weekly_activity_minutes=VALUES(weekly_activity_minutes)",
                CurrentUser.id(),input.effectiveFrom(),input.dailyCalories(),
                input.dailyProteinG(),input.weeklyActivityMinutes());
        return db.queryForObject("SELECT id,effective_from,daily_calories,daily_protein_g,weekly_activity_minutes " +
                "FROM prp_wellness_goals WHERE user_id=? AND effective_from=?",
                this::mapGoal,CurrentUser.id(),input.effectiveFrom());
    }
    private Goal goal(LocalDate date) {
        return db.query("SELECT id,effective_from,daily_calories,daily_protein_g,weekly_activity_minutes " +
                "FROM prp_wellness_goals WHERE user_id=? AND effective_from<=? ORDER BY effective_from DESC LIMIT 1",
                this::mapGoal,CurrentUser.id(),date).stream().findFirst().orElse(null);
    }
    public DailySummary daily(LocalDate date) {
        long u=CurrentUser.id();
        List<Meal> dayMeals=meals(date);
        BigDecimal calories=BigDecimal.ZERO,protein=BigDecimal.ZERO,carbs=BigDecimal.ZERO,fat=BigDecimal.ZERO;
        for(Meal m:dayMeals) for(MealItem i:m.items()){
            calories=calories.add(i.calories());protein=protein.add(i.proteinG());
            carbs=carbs.add(i.carbsG());fat=fat.add(i.fatG());
        }
        List<Exercise> ex=exercises(date);
        int minutes=ex.stream().mapToInt(Exercise::durationMinutes).sum();
        BigDecimal exKcal=ex.stream().map(Exercise::estimatedKcal).filter(Objects::nonNull)
                .reduce(BigDecimal.ZERO,BigDecimal::add);
        if(ex.stream().noneMatch(e->e.estimatedKcal()!=null)) exKcal=null;
        List<BigDecimal> weights=db.query("SELECT weight_kg FROM prp_wellness_body_metrics " +
                "WHERE user_id=? AND measured_on<=? ORDER BY measured_on DESC,id DESC LIMIT 1",
                (r,n)->r.getBigDecimal("weight_kg"),u,date);
        return new DailySummary(date,dayMeals.isEmpty()?null:calories,
                dayMeals.isEmpty()?null:protein, dayMeals.isEmpty()?null:carbs, dayMeals.isEmpty()?null:fat,
                dayMeals.size(),minutes,exKcal,weights.isEmpty()?null:weights.get(0),goal(date),
                dayMeals.stream().map(Meal::mealType).distinct().toList());
    }
    public List<TrendPoint> trends(int days) {
        if(days<1||days>90) throw new IllegalArgumentException("days must be 1..90");
        LocalDate end=today(),start=end.minusDays(days-1);
        long u=CurrentUser.id();
        Map<LocalDate,BigDecimal> calorieMap=new HashMap<>();
        db.query("SELECT m.meal_date,SUM(i.calories) AS total FROM prp_wellness_meals m " +
                "JOIN prp_wellness_meal_items i ON i.meal_id=m.id " +
                "WHERE m.user_id=? AND m.meal_date BETWEEN ? AND ? GROUP BY m.meal_date",
                r->{calorieMap.put(r.getObject("meal_date",LocalDate.class),r.getBigDecimal("total"));},
                u,start,end);
        Map<LocalDate,Integer> activity=new HashMap<>();
        db.query("SELECT performed_on,SUM(duration_minutes) AS total FROM prp_wellness_exercises " +
                "WHERE user_id=? AND performed_on BETWEEN ? AND ? GROUP BY performed_on",
                r->{activity.put(r.getObject("performed_on",LocalDate.class),r.getInt("total"));},
                u,start,end);
        Map<LocalDate,BigDecimal> weights=new HashMap<>();
        db.query("SELECT measured_on,weight_kg FROM prp_wellness_body_metrics " +
                "WHERE user_id=? AND measured_on BETWEEN ? AND ? ORDER BY id",
                r->{weights.put(r.getObject("measured_on",LocalDate.class),r.getBigDecimal("weight_kg"));},
                u,start,end);
        List<TrendPoint> result=new ArrayList<>();
        for(int i=0;i<days;i++){
            LocalDate date=start.plusDays(i);
            result.add(new TrendPoint(date,calorieMap.get(date),activity.get(date),weights.get(date)));
        }
        return result;
    }
}
