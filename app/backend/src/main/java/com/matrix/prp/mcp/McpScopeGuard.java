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
    private java.util.Set<Long> expandedUsers = java.util.Set.of();
    record VerifiedClient(String clientId, java.util.Set<String> grantedScopes) {
        VerifiedClient { grantedScopes = java.util.Set.copyOf(grantedScopes); }
    }
    /** Typed internally; only the transport decides whether OAuth can satisfy it. */
    static final class MissingScope extends ResponseStatusException {
        private final String requiredScope;
        MissingScope(String scope) {
            super(HttpStatus.FORBIDDEN, "MCP scope required: " + scope);
            this.requiredScope = scope;
        }
        String requiredScope() { return requiredScope; }
    }
    private String expandedClient = "https://chatgpt.com/oauth/client.json";

    @org.springframework.beans.factory.annotation.Autowired
    void configureExpandedUsers(
            @Value("${matrix-prp.mcp.expanded-user-ids:}") String configured,
            @Value("${matrix-prp.mcp.expanded-client-id:https://chatgpt.com/oauth/client.json}") String client) {
        var ids = new java.util.HashSet<Long>();
        if (configured != null && !configured.isBlank()) {
            for (String text : configured.split(",", -1)) {
                long id;
                try { id = Long.parseLong(text.trim()); }
                catch (NumberFormatException e) { throw new IllegalStateException("Invalid expanded MCP account allowlist"); }
                if (id <= 0 || !ids.add(id)) throw new IllegalStateException("Invalid expanded MCP account allowlist");
            }
        }
        if (!"https://chatgpt.com/oauth/client.json".equals(client))
            throw new IllegalStateException("Unreviewed expanded MCP client");
        expandedUsers = java.util.Set.copyOf(ids); expandedClient = client;
    }

    public McpScopeGuard(@Value("${matrix-prp.mcp.oauth.enabled:false}") boolean oauthEnabled) {
        this.oauthEnabled = oauthEnabled;
    }

    public void require(String scope) {
        CurrentUser.id();
        if (!oauthEnabled) return; // Legacy first-party JWT is for private pre-OAuth smoke tests only.
        var auth = SecurityContextHolder.getContext().getAuthentication();
        if (!"prp.tasks.read".equals(scope)) {
            if (!expandedUsers.contains(CurrentUser.id()) || auth == null
                    || !(auth.getDetails() instanceof VerifiedClient verified)
                    || !expandedClient.equals(verified.clientId())) {
                throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Expanded MCP capability is not enabled for this account and client");
            }
        }
        if (auth == null || auth.getAuthorities().stream()
            .noneMatch(authority -> ("SCOPE_" + scope).equals(authority.getAuthority()))) {
            if (auth != null && auth.getDetails() instanceof VerifiedClient verified
                    && verified.grantedScopes().contains(scope)) {
                throw new MissingScope(scope);
            }
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "MCP scope required: " + scope);
        }
    }
}
