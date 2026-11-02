package com.matrix.prp.mcp;

import com.matrix.prp.common.api.ApiResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;
import java.util.List;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * Owner-only consent and revocation APIs; explicitly NOT exposed as MCP tools.
 * Uses ordinary PRP login JWT, not an external OAuth token.
 */
@RestController
@RequestMapping("/api/mcp/clients")
@ConditionalOnProperty(prefix = "matrix-prp.mcp.oauth", name = "enabled", havingValue = "true")
public class McpClientGrantController {
    public record GrantRequest(@NotBlank @Size(max = 128) String clientId,
                               @NotEmpty List<String> scopes,
                               @NotBlank String password) {}
    public record TemporaryPairingRequest(@NotBlank @Size(max = 128) String clientId,
                                          @NotBlank String password) {}
    public record RevokeRequest(@NotBlank String clientId) {}
    private final McpClientGrantService service;

    public McpClientGrantController(McpClientGrantService service) {
        this.service = service;
    }

    @GetMapping
    public ResponseEntity<ApiResponse<List<McpClientGrantService.Grant>>> list() {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(ApiResponse.success(service.mine()));
    }

    @PostMapping
    public ResponseEntity<ApiResponse<McpClientGrantService.Grant>> authorize(
            @Valid @RequestBody GrantRequest input) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(ApiResponse.success(service.authorize(
                input.clientId(), input.scopes(), input.password())));
    }

    /** PRP owner-only, ten-minute task-read lease. Not a general MCP grant. */
    @PostMapping("/pairing")
    public ResponseEntity<ApiResponse<McpClientGrantService.Grant>> pairing(
            @Valid @RequestBody TemporaryPairingRequest input) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(ApiResponse.success(service.authorizeTemporaryPairing(
                input.clientId(), input.password())));
    }

    @PostMapping("/revoke")
    public ResponseEntity<ApiResponse<Void>> revoke(@Valid @RequestBody RevokeRequest input) {
        service.revoke(input.clientId());
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(ApiResponse.success());
    }
}
