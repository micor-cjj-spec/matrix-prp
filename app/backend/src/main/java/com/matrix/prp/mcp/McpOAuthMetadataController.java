package com.matrix.prp.mcp;

import jakarta.servlet.http.HttpServletRequest;
import java.net.URI;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

/** Public RFC 9728 resource metadata; NOT an OAuth authorization server. */
@RestController
@ConditionalOnProperty(prefix = "matrix-prp.mcp.oauth", name = "enabled", havingValue = "true")
public class McpOAuthMetadataController {
    public static final List<String> SCOPES = List.of(
        "prp.tasks.read", "prp.finance.read", "prp.wellness.read",
        "prp.write.create", "prp.write.status", "prp.write.confirm");

    private final String resource;
    private final String issuer;
    private final String metadata;

    public McpOAuthMetadataController(
        @Value("${matrix-prp.mcp.oauth.resource:}") String resource,
        @Value("${matrix-prp.mcp.oauth.issuer:}") String issuer) {
        this.resource = McpOAuthResourceServerConfig.strictHttps(resource, "MCP OAuth resource");
        this.issuer = McpOAuthResourceServerConfig.strictHttps(issuer, "MCP OAuth issuer");
        this.metadata = metadataUrl(this.resource);
    }

    static String metadataUrl(String resource) {
        URI target = URI.create(resource);
        return target.getScheme() + "://" + target.getRawAuthority()
            + "/.well-known/oauth-protected-resource" + target.getRawPath();
    }

    @GetMapping("/.well-known/oauth-protected-resource/**")
    public ResponseEntity<Map<String,Object>> protectedResource(HttpServletRequest request) {
        // The path in this public metadata endpoint must match the advertised
        // canonical MCP resource. Reject arbitrary alternate paths.
        if (!URI.create(metadata).getRawPath().equals(request.getRequestURI())) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Unknown MCP protected resource");
        }
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .header("Access-Control-Allow-Origin", "*")
            .body(Map.of(
                "resource", resource,
                "authorization_servers", List.of(issuer),
                "scopes_supported", SCOPES,
                "bearer_methods_supported", List.of("header"),
                "resource_name", "Matrix PRP MCP"));
    }
}
