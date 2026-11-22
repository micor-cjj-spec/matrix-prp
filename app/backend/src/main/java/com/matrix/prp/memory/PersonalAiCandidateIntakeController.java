package com.matrix.prp.memory;

import com.matrix.prp.common.api.ApiResponse;
import com.matrix.prp.memory.PersonalMemoryService.AiCandidate;
import com.matrix.prp.memory.PersonalMemoryService.Memory;
import java.util.List;
import org.springframework.context.annotation.Profile;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * First-party owner-authenticated T-008 candidate intake only.
 * Explicitly excluded from MCP; it never confirms any fact or calls a model.
 */
@RestController
@Profile("!test")
@RequestMapping("/api/memory/ai-candidates")
public final class PersonalAiCandidateIntakeController {
    private final PersonalAiCandidateIntakeService service;

    public PersonalAiCandidateIntakeController(PersonalAiCandidateIntakeService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<ApiResponse<List<Memory>>> submit(
            @RequestBody List<AiCandidate> candidates) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(ApiResponse.success(service.submit(candidates)));
    }
}
