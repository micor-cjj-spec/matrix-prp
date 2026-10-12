package com.matrix.prp.ai;

import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.common.api.ApiResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

/** New explicit-reviewed P4 API; legacy /api/ai/codex/jobs remains a disabled placeholder. */
@RestController
@RequestMapping("/api/ai/codex/requests")
public class CodexJobController {
    public record CreateRequest(@NotBlank String taskType,@NotBlank @Size(max=1500) String prompt) {}
    public record ApprovalRequest(@NotBlank String confirmation) {}
    private final CodexJobService jobs;
    public CodexJobController(CodexJobService jobs) { this.jobs=jobs; }
    private static void administrator() {
        Object principal=SecurityContextHolder.getContext().getAuthentication().getPrincipal();
        if (!(principal instanceof UserProfile profile) || !profile.administrator())
            throw new ResponseStatusException(HttpStatus.FORBIDDEN,"Administrator only");
    }
    private static <T> ResponseEntity<ApiResponse<T>> ok(T value) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(ApiResponse.success(value));
    }
    @GetMapping("/capabilities")
    public ResponseEntity<ApiResponse<Map<String,Object>>> capabilities() {
        administrator();return ok(jobs.capabilities());
    }
    @GetMapping
    public ResponseEntity<ApiResponse<List<CodexJobStore.Job>>> list() {
        administrator();return ok(jobs.list());
    }
    @GetMapping("/{id}")
    public ResponseEntity<ApiResponse<CodexJobService.Detail>> detail(@PathVariable String id) {
        administrator();return ok(jobs.detail(id));
    }
    @PostMapping
    public ResponseEntity<ApiResponse<CodexJobStore.Job>> create(@Valid @RequestBody CreateRequest request) {
        administrator();
        return ResponseEntity.status(HttpStatus.CREATED).cacheControl(CacheControl.noStore())
            .body(ApiResponse.success(jobs.create(request.taskType(),request.prompt())));
    }
    @PostMapping("/{id}/approve")
    public ResponseEntity<ApiResponse<CodexJobStore.Job>> approve(
            @PathVariable String id,@Valid @RequestBody ApprovalRequest approval) {
        administrator();
        return ResponseEntity.status(HttpStatus.ACCEPTED).cacheControl(CacheControl.noStore())
            .body(ApiResponse.success(jobs.approve(id,approval.confirmation())));
    }
    @PostMapping("/{id}/cancel")
    public ResponseEntity<ApiResponse<CodexJobStore.Job>> cancel(@PathVariable String id) {
        administrator();return ok(jobs.cancel(id));
    }
}
