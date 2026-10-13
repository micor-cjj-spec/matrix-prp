package com.matrix.prp.ai;

import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.common.api.ApiResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
@RequestMapping("/api/ai")
public class AiController {
    public record ChatRequest(@Size(max=36) String conversationId, @NotBlank @Size(max=4000) String content,
                              @Size(max=4) List<String> contextScopes, Boolean contextConsent, @Size(max=80) String contextToken) {}
    private final AiService service;
    public AiController(AiService service) { this.service = service; }

    @GetMapping("/conversations")
    public ApiResponse<List<AiStore.Conversation>> conversations() {
        return ApiResponse.success(service.conversations());
    }

    @GetMapping("/conversations/{id}/messages")
    public ApiResponse<List<AiStore.Message>> messages(
            @PathVariable String id,
            @RequestParam(required=false) Long beforeId,
            @RequestParam(defaultValue="200") int limit) {
        return ApiResponse.success(service.messages(id, beforeId, limit));
    }

    @GetMapping("/conversations/{id}/blocks")
    public ApiResponse<List<AiStore.MessageBlock>> blocks(@PathVariable String id) {
        return ApiResponse.success(service.blocks(id));
    }

    @GetMapping("/usage")
    public ApiResponse<Map<String,Object>> usage() { return ApiResponse.success(service.usage()); }

    @PostMapping(value="/chat/stream", produces=MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter chat(@Valid @RequestBody ChatRequest request) {
        return service.chat(request.conversationId(), request.content(), request.contextScopes(), request.contextToken());
    }

    public record CodexJobRequest(@NotBlank @Size(max=80) String taskType,
                                  @NotBlank @Size(max=300) String target) {}

    @PostMapping("/codex/jobs")
    public ApiResponse<Map<String,Object>> createCodexJob(@Valid @RequestBody CodexJobRequest request) {
        requireAdministrator();
        throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                "Codex Worker is not configured; no server execution in P0");
    }

    private static void requireAdministrator() {
        Object principal = SecurityContextHolder.getContext().getAuthentication().getPrincipal();
        if (!(principal instanceof UserProfile user) || !user.administrator())
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Administrator only");
    }

    /** P0 has no Codex execution capability, only an administrator-only placeholder. */
    @GetMapping("/codex/capabilities")
    public ApiResponse<Map<String,Object>> codexCapabilities() {
        requireAdministrator();
        return ApiResponse.success(Map.of("enabled", false, "status", "NOT_CONFIGURED",
                "message", "Codex Worker is reserved for a future isolated administrator-only phase"));
    }
}
