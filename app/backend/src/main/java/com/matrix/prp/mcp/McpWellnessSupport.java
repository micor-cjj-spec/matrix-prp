package com.matrix.prp.mcp;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.wellness.WellnessModels.*;
import com.matrix.prp.wellness.WellnessService;
import jakarta.validation.Valid;
import jakarta.validation.Validator;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

/** Typed structured health changes; no model-supplied owner, table, SQL or idempotency key. */
@Component
@ConditionalOnProperty(prefix="matrix-prp.mcp", name="enabled", havingValue="true")
public class McpWellnessSupport {
    public record Meal(@NotNull LocalDate mealDate, @NotBlank String mealType,
                       @Size(max=500) String note,
                       @NotEmpty @Size(max=30) List<WellnessService.AiMealItem> items) {}
    /** Exactly one of these fields, selected by entity, is accepted. Updates replace all fields. */
    public record Input(@Valid Meal meal, @Valid ExerciseInput exercise, @Valid BodyMetricInput metric) {}
    public record Change(String entity, long recordId, JsonNode before, Input after, JsonNode foods) {}
    private final JdbcTemplate db;
    private final WellnessService wellness;
    private final ObjectMapper json;
    private final Validator validator;
    public McpWellnessSupport(JdbcTemplate db, WellnessService wellness, ObjectMapper json, Validator validator) {
        this.db=db;this.wellness=wellness;this.json=json;this.validator=validator;
    }
    static ResponseStatusException bad(String message) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST,message);
    }
    static String table(String entity) {
        return switch(entity == null ? "" : entity) {
            case "meal" -> "prp_wellness_meals";
            case "exercise" -> "prp_wellness_exercises";
            case "metric" -> "prp_wellness_body_metrics";
            default -> throw bad("Entity must be meal, exercise or metric");
        };
    }
    // Read and normalize through the SAME JSON codec as the stored draft, including decimal nodes.
    private JsonNode snapshot(Object value) {
        try { return json.readTree(json.writeValueAsString(value)); }
        catch(Exception e) { throw bad("Invalid wellness payload"); }
    }
    public Object get(String entity,long id) {
        table(entity);
        if(id<=0) throw bad("Positive owned record ID required");
        return switch(entity) {
            case "meal" -> wellness.ownedMeal(id);
            case "exercise" -> wellness.ownedExercise(id);
            default -> wellness.ownedMetric(id);
        };
    }
    private JsonNode locked(String entity,long id) {
        if(id<=0) throw bad("Positive owned record ID required");
        // Table comes only from the fixed switch. Lock the parent before reading its item snapshot.
        var found=db.query("SELECT id FROM "+table(entity)+" WHERE id=? AND user_id=? FOR UPDATE",
            (rs,n)->rs.getLong(1),id,CurrentUser.id());
        if(found.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Wellness record not found");
        return snapshot(get(entity,id));
    }
    private void validate(String entity,Input input) {
        table(entity);
        if(input==null || !validator.validate(input).isEmpty()) throw bad("Invalid wellness fields");
        int fields=(input.meal()!=null?1:0)+(input.exercise()!=null?1:0)+(input.metric()!=null?1:0);
        if(fields!=1 || (entity.equals("meal") && input.meal()==null)
                || (entity.equals("exercise") && input.exercise()==null)
                || (entity.equals("metric") && input.metric()==null)) throw bad("Exactly one matching health input required");
        if(input.meal()!=null) {
            Meal meal=input.meal();
            if(!Set.of("BREAKFAST","LUNCH","DINNER","SNACK").contains(meal.mealType())) throw bad("Invalid meal type");
            for(var item:meal.items()) {
                if(item==null) throw bad("Missing meal item");
                if(item.foodId()!=null && item.foodId()>0) {
                    if(item.grams()==null || item.grams().compareTo(new BigDecimal("0.1"))<0
                            || item.grams().compareTo(new BigDecimal("3000"))>0
                            || item.calories()!=null || item.name()!=null) throw bad("Catalog item needs only foodId and grams");
                } else {
                    if(item.foodId()!=null || item.name()==null || item.name().isBlank() || item.name().length()>120
                            || item.calories()==null || item.calories().signum()<=0
                            || item.calories().compareTo(new BigDecimal("20000"))>0 || item.calories().scale()>2
                            || item.grams()!=null && (item.grams().signum()<0 || item.grams().compareTo(new BigDecimal("3000"))>0))
                        throw bad("Estimated food requires a name and explicit event calories");
                }
            }
        }
    }
    private JsonNode catalog(Input input) {
        var foods=new java.util.TreeMap<Long,Food>();
        if(input!=null && input.meal()!=null) {
            // Stable lock ordering; public or current-owner catalog entries only.
            var ids=input.meal().items().stream().filter(i->i.foodId()!=null)
                .map(WellnessService.AiMealItem::foodId).distinct().sorted().toList();
            for(long id:ids) {
                var rows=db.query("SELECT id FROM prp_wellness_foods WHERE id=? AND (owner_user_id IS NULL OR owner_user_id=?) FOR UPDATE",
                    (rs,n)->rs.getLong(1),id,CurrentUser.id());
                if(rows.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Food unavailable");
                foods.put(id,wellness.accessibleFood(id));
            }
        }
        return snapshot(foods);
    }
    /** Called only inside McpDraftService's transaction; proposal is never an immediate write. */
    public Change capture(String entity,long id,Input input,boolean delete) {
        table(entity);
        if(id<0 || delete && id==0) throw bad("Invalid record ID");
        if(delete && input!=null) throw bad("Delete has no replacement fields");
        if(!delete) validate(entity,input);
        JsonNode before=id==0?null:locked(entity,id);
        return new Change(entity,id,before,input,catalog(input));
    }
    public void validateChange(Change change,boolean create,boolean delete) {
        if(change==null) throw bad("Wellness change required");
        table(change.entity());
        boolean hasBefore=change.before()!=null && !change.before().isNull();
        if(create ? change.recordId()!=0 || hasBefore : change.recordId()<=0 || !hasBefore)
            throw bad("Invalid wellness operation target");
        if(delete ? change.after()!=null : change.after()==null) throw bad("Invalid replacement fields");
        if(!delete) validate(change.entity(),change.after());
        if(change.foods()==null) throw bad("Food snapshot required");
    }
    public Object apply(Change change,String draftId,boolean create,boolean delete) {
        validateChange(change,create,delete);
        if(!create && !locked(change.entity(),change.recordId()).equals(change.before()))
            throw new ResponseStatusException(HttpStatus.CONFLICT,"Health record changed; prepare and approve again");
        if(!catalog(change.after()).equals(change.foods()))
            throw new ResponseStatusException(HttpStatus.CONFLICT,"Food changed; prepare and approve again");
        long id=change.recordId();
        if(delete) {
            switch(change.entity()) {
                case "meal" -> wellness.deleteMeal(id);
                case "exercise" -> wellness.deleteExercise(id);
                default -> wellness.deleteMetric(id);
            }
            return Map.of("entity",change.entity(),"recordId",id,"deleted",true);
        }
        Input input=change.after();
        return switch(change.entity()) {
            case "meal" -> {
                Meal m=input.meal();
                yield create ? wellness.addAiMeal(m.mealDate(),m.mealType(),m.note(),m.items(),"mcp:"+draftId)
                    : wellness.updateAiMeal(id,m.mealDate(),m.mealType(),m.note(),m.items());
            }
            case "exercise" -> create?wellness.addExercise(input.exercise()):wellness.updateExercise(id,input.exercise());
            default -> create?wellness.addMetric(input.metric()):wellness.updateMetric(id,input.metric());
        };
    }
}
