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

@RestController
@RequestMapping("/api/ai/agent")
public class AgentTaskController {
    public record DraftRequest(@NotBlank String taskType, @NotBlank @Size(max=2000) String prompt) {}
    public record ApprovalRequest(@NotBlank String confirmation) {}
    private final AgentTaskService tasks;
    public AgentTaskController(AgentTaskService tasks) { this.tasks = tasks; }
    private static void requireAdmin() {
        Object principal = SecurityContextHolder.getContext().getAuthentication().getPrincipal();
        if (!(principal instanceof UserProfile user) || !user.administrator())
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Administrator only");
    }
    @GetMapping("/capabilities")
    public ResponseEntity<ApiResponse<Map<String, Object>>> capabilities() {
        requireAdmin();
        return ok(tasks.capabilities());
    }
    @GetMapping("/tasks")
    public ResponseEntity<ApiResponse<List<AgentTaskStore.AgentTask>>> list() {
        requireAdmin();
        return ok(tasks.list());
    }
    @GetMapping("/tasks/{id}")
    public ResponseEntity<ApiResponse<AgentTaskStore.AgentTask>> get(@PathVariable String id) {
        requireAdmin();
        return ok(tasks.find(id));
    }
    @PostMapping("/tasks")
    public ResponseEntity<ApiResponse<AgentTaskStore.AgentTask>> create(@Valid @RequestBody DraftRequest request) {
        requireAdmin();
        return ResponseEntity.status(HttpStatus.CREATED).cacheControl(CacheControl.noStore())
            .body(ApiResponse.success(tasks.create(request.taskType(), request.prompt())));
    }
    @PostMapping("/tasks/{id}/approve")
    public ResponseEntity<ApiResponse<AgentTaskStore.AgentTask>> approve(
        @PathVariable String id, @Valid @RequestBody ApprovalRequest request) {
        requireAdmin();
        return ResponseEntity.status(HttpStatus.ACCEPTED).cacheControl(CacheControl.noStore())
            .body(ApiResponse.success(tasks.approve(id, request.confirmation())));
    }
    @PostMapping("/tasks/{id}/cancel")
    public ResponseEntity<ApiResponse<AgentTaskStore.AgentTask>> cancel(@PathVariable String id) {
        requireAdmin();
        return ok(tasks.cancel(id));
    }
    private static <T> ResponseEntity<ApiResponse<T>> ok(T data) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(ApiResponse.success(data));
    }
}
