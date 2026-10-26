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
        var expected = java.util.Set.of("prp_tasks_list", "prp_task_get", "prp_finance_month",
            "prp_wellness_daily", "prp_prepare_task", "prp_prepare_finance", "prp_prepare_record",
            "prp_draft_status", "prp_confirm_draft", "prp_prepare_task_update", "prp_prepare_task_delete");
        var actual = definitions.stream().map(spec -> spec.tool().name()).collect(java.util.stream.Collectors.toSet());
        if (definitions.size() != expected.size() || !actual.equals(expected)) {
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
