package com.matrix.prp.wellness;

import com.matrix.prp.common.api.ApiResponse;
import com.matrix.prp.wellness.WellnessModels.*;
import jakarta.validation.Valid;
import java.time.LocalDate;
import java.util.List;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.*;

@RestController
@org.springframework.context.annotation.Profile("!test")
@RequestMapping("/api/wellness")
public class WellnessController {
    private final WellnessService service;
    private final UsdaFoodCatalog usda;
    public WellnessController(WellnessService service, UsdaFoodCatalog usda) { this.service = service; this.usda = usda; }

    /** Reusable personal servings; separate from public/standard nutrition foods. */
    @GetMapping("/dishes")
    public ApiResponse<List<DishTemplate>> dishes(@RequestParam(defaultValue="") String q) {
        return ApiResponse.success(service.dishTemplates(q));
    }
    @GetMapping("/dishes/{id}")
    public ApiResponse<DishTemplate> dish(@PathVariable long id) {
        return ApiResponse.success(service.ownedDishTemplate(id));
    }
    @PostMapping("/dishes")
    public ApiResponse<DishTemplate> saveDish(@Valid @RequestBody DishTemplateInput input) {
        return ApiResponse.success(service.saveDishTemplate(input));
    }
    @PutMapping("/dishes/{id}")
    public ApiResponse<DishTemplate> updateDish(@PathVariable long id,@Valid @RequestBody DishTemplateInput input) {
        return ApiResponse.success(service.updateDishTemplate(id,input));
    }
    @DeleteMapping("/dishes/{id}")
    public ApiResponse<Void> deleteDish(@PathVariable long id) {
        service.deleteDishTemplate(id);
        return ApiResponse.success();
    }

    @GetMapping("/foods")
    public ApiResponse<List<Food>> foods(@RequestParam(defaultValue="") String q) { return ApiResponse.success(service.foods(q)); }
    /** Exact ID lookup ensures unknown weight drafts show the actual matching food's kcal/100g. */
    @GetMapping("/foods/{id}")
    public ApiResponse<Food> food(@PathVariable long id) {
        return ApiResponse.success(service.accessibleFood(id));
    }
    @GetMapping("/foods/usda/status")
    public ApiResponse<java.util.Map<String,Boolean>> usdaStatus() {
        return ApiResponse.success(java.util.Map.of("configured", usda.configured()));
    }
    @GetMapping("/foods/usda/search")
    public ApiResponse<List<UsdaFoodCatalog.Candidate>> searchUsda(@RequestParam String q) {
        return ApiResponse.success(usda.search(q));
    }
    @PostMapping("/foods/usda/{id}/import")
    public ApiResponse<Food> importUsda(@PathVariable long id, @RequestParam(required=false) String alias) {
        var candidate = usda.detail(id);
        return ApiResponse.success(service.importUsda(candidate,alias));
    }
    @GetMapping("/foods/frequent")
    public ApiResponse<List<Food>> frequentFoods() { return ApiResponse.success(service.frequentFoods()); }
    @PostMapping("/foods")
    public ApiResponse<Food> addFood(@Valid @RequestBody FoodInput request) { return ApiResponse.success(service.addFood(request)); }

    @GetMapping("/meals")
    public ApiResponse<List<Meal>> meals(@RequestParam @DateTimeFormat(iso=DateTimeFormat.ISO.DATE) LocalDate date) {
        return ApiResponse.success(service.meals(date));
    }
    @PostMapping("/meals")
    public ApiResponse<Meal> addMeal(@Valid @RequestBody MealInput request) { return ApiResponse.success(service.addMeal(request)); }
    @PutMapping("/meals/{id}")
    public ApiResponse<Meal> updateMeal(@PathVariable long id, @Valid @RequestBody MealInput request) {
        return ApiResponse.success(service.updateMeal(id, request));
    }
    @DeleteMapping("/meals/{id}")
    public ApiResponse<Void> deleteMeal(@PathVariable long id) { service.deleteMeal(id); return ApiResponse.success(); }
    @PostMapping("/meals/{id}/copy")
    public ApiResponse<Meal> copyMeal(@PathVariable long id, @RequestParam @DateTimeFormat(iso=DateTimeFormat.ISO.DATE) LocalDate date) {
        return ApiResponse.success(service.copyMeal(id, date));
    }

    @GetMapping("/exercises")
    public ApiResponse<List<Exercise>> exercises(@RequestParam @DateTimeFormat(iso=DateTimeFormat.ISO.DATE) LocalDate date) {
        return ApiResponse.success(service.exercises(date));
    }
    @PostMapping("/exercises")
    public ApiResponse<Exercise> addExercise(@Valid @RequestBody ExerciseInput request) {
        return ApiResponse.success(service.addExercise(request));
    }
    @PutMapping("/exercises/{id}")
    public ApiResponse<Exercise> updateExercise(@PathVariable long id, @Valid @RequestBody ExerciseInput request) {
        return ApiResponse.success(service.updateExercise(id, request));
    }
    @DeleteMapping("/exercises/{id}")
    public ApiResponse<Void> deleteExercise(@PathVariable long id) { service.deleteExercise(id); return ApiResponse.success(); }

    @GetMapping("/body-metrics")
    public ApiResponse<List<BodyMetric>> metrics(@RequestParam(defaultValue="30") int days) {
        return ApiResponse.success(service.metrics(days));
    }
    @PostMapping("/body-metrics")
    public ApiResponse<BodyMetric> addMetric(@Valid @RequestBody BodyMetricInput request) {
        return ApiResponse.success(service.addMetric(request));
    }
    @PutMapping("/body-metrics/{id}")
    public ApiResponse<BodyMetric> updateMetric(@PathVariable long id, @Valid @RequestBody BodyMetricInput request) {
        return ApiResponse.success(service.updateMetric(id, request));
    }
    @DeleteMapping("/body-metrics/{id}")
    public ApiResponse<Void> deleteMetric(@PathVariable long id) { service.deleteMetric(id); return ApiResponse.success(); }

    @GetMapping("/goals")
    public ApiResponse<List<Goal>> goals() { return ApiResponse.success(service.goals()); }
    @PostMapping("/goals")
    public ApiResponse<Goal> saveGoal(@Valid @RequestBody GoalInput request) { return ApiResponse.success(service.saveGoal(request)); }
    @GetMapping("/profile")
    public ApiResponse<Profile> profile() { return ApiResponse.success(service.profile()); }
    @PutMapping("/profile")
    public ApiResponse<Profile> saveProfile(@Valid @RequestBody ProfileInput request) { return ApiResponse.success(service.saveProfile(request)); }

    @GetMapping("/summary/daily")
    public ApiResponse<DailySummary> summary(@RequestParam @DateTimeFormat(iso=DateTimeFormat.ISO.DATE) LocalDate date) {
        return ApiResponse.success(service.daily(date));
    }
    @GetMapping("/summary/trends")
    public ApiResponse<List<TrendPoint>> trends(@RequestParam(defaultValue="30") int days) {
        return ApiResponse.success(service.trends(days));
    }
}
