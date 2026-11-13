package com.matrix.prp.wellness;

import com.matrix.prp.common.api.ApiResponse;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Only the first-party authenticated Web can verify an existing package label.
 * No model/MCP write tool is exposed for this operation.
 */
@RestController
@Profile("!test")
@RequestMapping("/api/wellness/meals")
public class WellnessLabelVerificationController {
    private final WellnessLabelVerificationService service;

    public WellnessLabelVerificationController(WellnessLabelVerificationService service) {
        this.service=service;
    }

    @PostMapping("/{id}/label-verification")
    public ApiResponse<WellnessNutritionDetailsService.MealDetails> verify(
            @PathVariable long id,
            @RequestBody WellnessLabelVerificationService.LabelInput request) {
        return ApiResponse.success(service.confirm(id,request));
    }
}
