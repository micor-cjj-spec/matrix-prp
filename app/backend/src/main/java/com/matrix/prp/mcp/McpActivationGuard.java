package com.matrix.prp.mcp;

import java.util.Arrays;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

/**
 * Fail closed on accidental public MCP activation without OAuth.
 * The old JWT-only MCP route is retained for isolated test profiles only.
 * A non-test runtime cannot expose MCP, even read-only, without OAuth.
 */
@Component
public class McpActivationGuard {
    public McpActivationGuard(Environment environment,
        @Value("${matrix-prp.mcp.enabled:false}") boolean mcpEnabled,
        @Value("${matrix-prp.mcp.oauth.enabled:false}") boolean oauthEnabled,
        @Value("${matrix-prp.mcp.write-enabled:false}") boolean writeEnabled) {
        verify(mcpEnabled, oauthEnabled, writeEnabled,
            Arrays.asList(environment.getActiveProfiles()));
    }

    static void verify(boolean mcp, boolean oauth, boolean write,
                       java.util.List<String> activeProfiles) {
        if (write && !mcp) {
            throw new IllegalStateException("MCP write requires the MCP service to be enabled");
        }
        if (oauth && !mcp) {
            throw new IllegalStateException("MCP OAuth requires the MCP service to be enabled");
        }
        boolean isolatedTests = activeProfiles.stream()
            .anyMatch(p -> "test".equals(p) || "video-integration".equals(p));
        if (mcp && !oauth && !isolatedTests) {
            throw new IllegalStateException("Public PRP MCP requires OAuth. Legacy PRP JWT tools may be used only in isolated tests");
        }
    }
}
