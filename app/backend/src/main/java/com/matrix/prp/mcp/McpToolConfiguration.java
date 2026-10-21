package com.matrix.prp.mcp;

import io.modelcontextprotocol.server.McpStatelessServerFeatures;
import java.util.List;
import org.springaicommunity.mcp.provider.tool.SyncStatelessMcpToolProvider;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Explicit opt-in MCP capability manifest.
 *
 * Avoid relying on annotation BeanPostProcessor ordering when the MCP
 * server initializes. Never auto-publish unrelated PRP AI callbacks.
 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(prefix = "matrix-prp.mcp", name = "enabled", havingValue = "true")
public class McpToolConfiguration {
    @Bean
    public List<McpStatelessServerFeatures.SyncToolSpecification> prpMcpSpecifications(PrpMcpTools tools) {
        var definitions = new SyncStatelessMcpToolProvider(List.of(tools)).getToolSpecifications();
        if (definitions.size() != 8) {
            throw new IllegalStateException("PRP MCP tool allowlist mismatch; refusing to start");
        }
        return List.copyOf(definitions);
    }
}
