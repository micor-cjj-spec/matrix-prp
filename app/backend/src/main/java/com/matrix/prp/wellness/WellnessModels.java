package com.matrix.prp.wellness;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

public final class WellnessModels {
    private WellnessModels() {}

    public record Food(long id, String name, String preparation, BigDecimal calories100g,
                       BigDecimal protein100g, BigDecimal carbs100g, BigDecimal fat100g,
                       String sourceNote, boolean custom) {}
    public record FoodInput(@NotBlank @Size(max=120) String name, String preparation,
                            @NotNull @DecimalMin("0") @DecimalMax("900") BigDecimal calories100g,
                            @NotNull @DecimalMin("0") @DecimalMax("100") BigDecimal protein100g,
                            @NotNull @DecimalMin("0") @DecimalMax("100") BigDecimal carbs100g,
                            @NotNull @DecimalMin("0") @DecimalMax("100") BigDecimal fat100g,
                            @Size(max=255) String sourceNote) {}
    public record MealItem(long id, long foodId, String foodName, BigDecimal grams, BigDecimal calories,
                           BigDecimal proteinG, BigDecimal carbsG, BigDecimal fatG, boolean estimate) {}
    public record Meal(long id, LocalDate mealDate, String mealType, String note, List<MealItem> items) {}
    public record ItemInput(@NotNull @Positive Long foodId,
                            @NotNull @DecimalMin("0.1") @DecimalMax("10000") BigDecimal grams) {}
    public record MealInput(@NotNull LocalDate mealDate, @NotBlank String mealType,
                            @Size(max=500) String note,
                            @NotEmpty @Size(max=50) List<@NotNull @Valid ItemInput> items,
                            @Size(max=80) String idempotencyKey) {}
    public record Exercise(long id, LocalDate performedOn, String name, int durationMinutes,
                           BigDecimal estimatedKcal, String note) {}
    public record ExerciseInput(@NotNull LocalDate performedOn, @NotBlank @Size(max=100) String name,
                                @Min(1) @Max(1440) int durationMinutes,
                                @DecimalMin("0") @DecimalMax("20000") BigDecimal estimatedKcal,
                                @Size(max=500) String note) {}
    public record BodyMetric(long id, LocalDate measuredOn, BigDecimal weightKg,
                             BigDecimal bodyFatPct, BigDecimal waistCm) {}
    public record BodyMetricInput(@NotNull LocalDate measuredOn,
                                  @NotNull @DecimalMin("0.1") @DecimalMax("500") BigDecimal weightKg,
                                  @DecimalMin("0") @DecimalMax("100") BigDecimal bodyFatPct,
                                  @DecimalMin("0") @DecimalMax("300") BigDecimal waistCm) {}
    public record Goal(long id, LocalDate effectiveFrom, BigDecimal dailyCalories,
                       BigDecimal dailyProteinG, Integer weeklyActivityMinutes) {}
    public record GoalInput(@NotNull LocalDate effectiveFrom,
                            @NotNull @DecimalMin("100") @DecimalMax("10000") BigDecimal dailyCalories,
                            @DecimalMin("0") @DecimalMax("1000") BigDecimal dailyProteinG,
                            @Min(0) @Max(10080) Integer weeklyActivityMinutes) {}
    public record Profile(BigDecimal heightCm, String timezone) {}
    public record ProfileInput(@DecimalMin("30") @DecimalMax("300") BigDecimal heightCm,
                               @NotBlank String timezone) {}
    public record DailySummary(LocalDate date, BigDecimal calories, BigDecimal proteinG,
                               BigDecimal carbsG, BigDecimal fatG, int mealCount,
                               int exerciseMinutes, BigDecimal exerciseEstimatedKcal,
                               BigDecimal latestWeightKg, Goal goal, List<String> recordedMealTypes) {}
    public record TrendPoint(LocalDate date, BigDecimal calories, Integer exerciseMinutes,
                             BigDecimal weightKg) {}
}
