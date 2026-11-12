package com.matrix.prp.mcp;

import io.modelcontextprotocol.server.McpStatelessServerFeatures;
import io.modelcontextprotocol.spec.McpSchema;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;

/**
 * Static, sandboxed MCP Apps approval UI. Never embeds OAuth credentials or
 * user records in its template: the host supplies the tool result after auth.
 * OFF unless the explicitly reviewed ChatGPT UI rollout flag is enabled.
 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(prefix = "matrix-prp.mcp",
    name = "chatgpt-health-approval-ui-enabled", havingValue = "true")
public class McpWellnessApprovalUiConfiguration {
    public static final String RESOURCE_URI = "ui://prp/wellness-approval";
    public static final String MIME = "text/html;profile=mcp-app";

    @Bean
    public List<McpStatelessServerFeatures.SyncResourceSpecification> prpChatgptApprovalResource() {
        try {
            var input = new ClassPathResource("mcp/wellness-approval.html");
            String html = new String(input.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
            var resource = McpSchema.Resource.builder()
                .uri(RESOURCE_URI)
                .name("PRP wellness creation approval card")
                .description("User-operated approval in ChatGPT; does not open the PRP application")
                .mimeType(MIME)
                .build();
            return List.of(new McpStatelessServerFeatures.SyncResourceSpecification(
                resource, (context, request) -> new McpSchema.ReadResourceResult(
                    List.of(new McpSchema.TextResourceContents(request.uri(), MIME, html))
                )));
        } catch (Exception e) {
            throw new IllegalStateException("MCP approval UI resource unavailable", e);
        }
    }
}
