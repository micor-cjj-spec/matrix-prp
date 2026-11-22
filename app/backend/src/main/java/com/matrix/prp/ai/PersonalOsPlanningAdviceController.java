package com.matrix.prp.ai;

import com.matrix.prp.common.api.ApiResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.context.annotation.Profile;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * First-party interactive flow ONLY: inspect exact content and provider,
 * confirm once, then request one model suggestion. Deliberately not MCP.
 */
@RestController
@Profile("!test")
@RequestMapping("/api/ai/personal-os/goals/{goalId}/model")
public final class PersonalOsPlanningAdviceController {
    public record Options(Boolean includePersonalFacts) {}
    public record ConfirmRequest(@NotBlank String previewId) {}
    public record SuggestRequest(@NotBlank String modelToken) {}

    private final PersonalOsPlanningAdviceService service;

    public PersonalOsPlanningAdviceController(PersonalOsPlanningAdviceService service) {
        this.service = service;
    }

    @PostMapping("/preview")
    public ResponseEntity<ApiResponse<PersonalOsPlanningAdviceService.Review>> preview(
            @PathVariable long goalId, @RequestBody(required = false) Options options) {
        return noStore(ApiResponse.success(service.preview(goalId,
            options != null && Boolean.TRUE.equals(options.includePersonalFacts()))));
    }

    @PostMapping("/confirm")
    public ResponseEntity<ApiResponse<PersonalOsPlanningAdviceService.Approved>> confirm(
            @PathVariable long goalId, @Valid @RequestBody ConfirmRequest request) {
        return noStore(ApiResponse.success(service.confirm(goalId, request.previewId())));
    }

    @PostMapping("/suggest")
    public ResponseEntity<ApiResponse<PersonalOsPlanningAdviceService.Advice>> suggest(
            @PathVariable long goalId, @Valid @RequestBody SuggestRequest request) {
        return noStore(ApiResponse.success(service.suggest(goalId, request.modelToken())));
    }

    private static <T> ResponseEntity<ApiResponse<T>> noStore(ApiResponse<T> value) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(value);
    }
}
