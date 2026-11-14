package com.matrix.prp.ai;

import com.matrix.prp.common.api.ApiResponse;
import org.springframework.context.annotation.Profile;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * Authenticated first-party preview; intentionally absent from AI/MCP tool
 * registries. A preview never grants third-party model sharing consent.
 */
@RestController
@Profile("!test")
@RequestMapping("/api/ai/personal-os")
public final class PersonalOsPlanningPreviewController {
    public record Options(Boolean includePersonalFacts) {}
    private final PersonalOsPlanningPreviewService service;

    public PersonalOsPlanningPreviewController(PersonalOsPlanningPreviewService service) {
        this.service = service;
    }

    @PostMapping("/goals/{goalId}/preview")
    public ResponseEntity<ApiResponse<PersonalOsPlanningPreviewService.Preview>> preview(
            @PathVariable long goalId, @RequestBody(required = false) Options options) {
        boolean selected = options != null && Boolean.TRUE.equals(options.includePersonalFacts());
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(ApiResponse.success(service.preview(goalId, selected)));
    }
}
