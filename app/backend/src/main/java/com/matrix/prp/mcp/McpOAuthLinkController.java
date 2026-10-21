package com.matrix.prp.mcp;

import com.matrix.prp.common.api.ApiResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;

/**
 * This entry point accepts ONLY an independently validated external OAuth JWT.
 * It cannot be called with a PRP login token and never accepts a user ID/sub.
 */
@RestController
@ConditionalOnProperty(prefix = "matrix-prp.mcp.oauth", name = "enabled", havingValue = "true")
public class McpOAuthLinkController {
    public record CompleteRequest(@NotBlank String ticket) {}
    private final McpIdentityLinkService links;

    public McpOAuthLinkController(McpIdentityLinkService links) { this.links = links; }

    @PostMapping("/api/mcp/link")
    public ResponseEntity<ApiResponse<McpIdentityLinkService.Link>> complete(
            @AuthenticationPrincipal Jwt jwt, @Valid @RequestBody CompleteRequest request) {
        if (jwt == null || jwt.getIssuer() == null || jwt.getSubject() == null)
            throw new org.springframework.web.server.ResponseStatusException(
                org.springframework.http.HttpStatus.UNAUTHORIZED, "Valid OAuth identity is required");
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(ApiResponse.success(links.complete(
                request.ticket(), jwt.getIssuer().toString(), jwt.getSubject(),
                jwt.getClaimAsString("client_id"))));
    }
}
