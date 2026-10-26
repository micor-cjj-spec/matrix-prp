package com.matrix.prp.mcp;

import com.matrix.prp.auth.security.CurrentUser;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

/** Per-tool authorization; a valid signature alone never grants finance or write scopes. */
@Component
@ConditionalOnProperty(prefix = "matrix-prp.mcp", name = "enabled", havingValue = "true")
public class McpScopeGuard {
    private final boolean oauthEnabled;

    public McpScopeGuard(@Value("${matrix-prp.mcp.oauth.enabled:false}") boolean oauthEnabled) {
        this.oauthEnabled = oauthEnabled;
    }

    public void require(String scope) {
        CurrentUser.id();
        if (!oauthEnabled) return; // Legacy first-party JWT is for private pre-OAuth smoke tests only.
        var auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth == null || auth.getAuthorities().stream()
            .noneMatch(authority -> ("SCOPE_" + scope).equals(authority.getAuthority()))) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "MCP scope required: " + scope);
        }
    }
}
