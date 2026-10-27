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
 * Both endpoints require the first-party PRP session JWT and always send
 * no-store. The Keycloak redirect is handled by a PRP SPA page, which removes
 * query data from browser history before posting to /finish.
 *
 * These are NOT public OAuth callback endpoints and NEVER accept external
 * Bearer tokens; they use PRP's ordinary /api/** auth chain.
 */
@RestController
@RequestMapping("/api/mcp/identity/oidc")
@ConditionalOnProperty(prefix = "matrix-prp.mcp.oauth.first-party-link",
                       name = "enabled", havingValue = "true")
public class McpFirstPartyOidcLinkController {
    record StartRequest(@NotBlank String password) {}
    record FinishRequest(
        @NotBlank @Size(max = 128) String state,
        @NotBlank @Size(max = 4096) String code,
        @NotBlank String iss) {}

    private final McpFirstPartyOidcLinkService links;

    public McpFirstPartyOidcLinkController(McpFirstPartyOidcLinkService links) {
        this.links = links;
    }

    @PostMapping("/start")
    public ResponseEntity<ApiResponse<McpFirstPartyOidcLinkService.Begin>> start(
            @Valid @RequestBody StartRequest input) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(ApiResponse.success(links.begin(input.password())));
    }

    @PostMapping("/finish")
    public ResponseEntity<ApiResponse<McpFirstPartyOidcLinkService.Finish>> finish(
            @Valid @RequestBody FinishRequest input) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(ApiResponse.success(links.finish(input.state(), input.code(), input.iss())));
    }
}
