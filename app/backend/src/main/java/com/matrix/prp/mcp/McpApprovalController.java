package com.matrix.prp.mcp;

import com.matrix.prp.common.api.ApiResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * Human-only approval surface, independent of MCP's tools/list and tools/call.
 * Requires the logged-in PRP account password for the exact immutable draft.
 */
@RestController
@RequestMapping("/api/mcp/approval")
@ConditionalOnProperty(prefix = "matrix-prp.mcp", name = "enabled", havingValue = "true")
public class McpApprovalController {
    public record ApproveRequest(@NotBlank @Size(max = 256) String password) {}
    private final McpDraftService drafts;

    public McpApprovalController(McpDraftService drafts) { this.drafts = drafts; }

    @GetMapping("/drafts/{id}")
    public ResponseEntity<ApiResponse<McpDraftService.Review>> review(@PathVariable String id) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(ApiResponse.success(drafts.review(id)));
    }

    @PostMapping("/drafts/{id}/approve")
    public ResponseEntity<ApiResponse<McpDraftService.Approval>> approve(
            @PathVariable String id, @Valid @RequestBody ApproveRequest request) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(ApiResponse.success(drafts.approve(id, request.password())));
    }

    @PostMapping("/drafts/{id}/reject")
    public ResponseEntity<ApiResponse<Void>> reject(@PathVariable String id) {
        drafts.reject(id);
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(ApiResponse.success());
    }
}
