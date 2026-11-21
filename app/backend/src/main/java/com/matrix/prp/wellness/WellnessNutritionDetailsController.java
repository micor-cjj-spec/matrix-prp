package com.matrix.prp.wellness;

import com.matrix.prp.common.api.ApiResponse;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Enriched confirmed-meal reads; separate from the stable V1 wellness routes.
 * Ownership is enforced by WellnessService and again in both detail queries.
 */
@RestController
@Profile("!test")
@RequestMapping("/api/wellness/meals")
public class WellnessNutritionDetailsController {
    private final WellnessNutritionDetailsService service;

    public WellnessNutritionDetailsController(WellnessNutritionDetailsService service) {
        this.service = service;
    }

    @GetMapping("/{id}/analysis")
    public ApiResponse<WellnessNutritionDetailsService.MealDetails> analysis(
            @PathVariable long id) {
        return ApiResponse.success(service.readOwnedMeal(id));
    }
}
