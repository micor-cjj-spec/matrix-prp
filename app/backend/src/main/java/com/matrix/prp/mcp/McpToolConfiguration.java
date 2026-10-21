package com.matrix.prp.mcp;

import com.matrix.prp.auth.model.UserProfile;
import io.modelcontextprotocol.server.McpStatelessServerFeatures;
import java.util.List;
import org.springaicommunity.mcp.provider.tool.SyncStatelessMcpToolProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

/**
 * Fixed PRP tool manifest. In OAuth mode the verified identity is captured by
 * the HTTP transport, carried in MCP's server-owned transport context, and
 * restored only while a tool executes (including on a different worker thread).
 * Never trust a model-supplied tool argument or _meta as an identity.
 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(prefix = "matrix-prp.mcp", name = "enabled", havingValue = "true")
public class McpToolConfiguration {
    @Bean
    public List<McpStatelessServerFeatures.SyncToolSpecification> prpMcpSpecifications(
            PrpMcpTools tools, @Value("${matrix-prp.mcp.oauth.enabled:false}") boolean oauthEnabled) {
        var definitions = new SyncStatelessMcpToolProvider(List.of(tools)).getToolSpecifications();
        if (definitions.size() != 8) {
            throw new IllegalStateException("PRP MCP tool allowlist mismatch; refusing to start");
        }
        if (!oauthEnabled) return List.copyOf(definitions);
        return definitions.stream().map(spec -> new McpStatelessServerFeatures.SyncToolSpecification(
            spec.tool(),
            (transport, request) -> {
                Object candidate = transport.get(McpOAuthTransportConfiguration.VERIFIED_AUTH);
                if (!(candidate instanceof Authentication auth)
                        || !auth.isAuthenticated()
                        || !(auth.getPrincipal() instanceof UserProfile)) {
                    throw new org.springframework.security.authentication.BadCredentialsException(
                        "Missing verified OAuth request identity");
                }
                var oldContext = SecurityContextHolder.getContext();
                var perCallContext = SecurityContextHolder.createEmptyContext();
                perCallContext.setAuthentication(auth);
                SecurityContextHolder.setContext(perCallContext);
                try {
                    return spec.callHandler().apply(transport, request);
                } finally {
                    SecurityContextHolder.setContext(oldContext);
                }
            }
        )).toList();
    }
}
