package com.matrix.prp.mcp;

import io.modelcontextprotocol.server.McpStatelessServerFeatures;
import io.modelcontextprotocol.spec.McpSchema;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(prefix = "matrix-prp.mcp", name = "chatgpt-task-approval-ui-enabled", havingValue = "true")
public class McpTaskApprovalUiConfiguration {
    static final String TEST_RESOURCE = "https://prp-test.micor.top/api/mcp";
    static final String RESOURCE_URI = "ui://prp/task-create-approval";

    @Bean
    List<McpStatelessServerFeatures.SyncResourceSpecification> prpTaskApprovalResources(
            @Value("${matrix-prp.mcp.oauth.resource:}") String resource,
            @Value("${matrix-prp.mcp.oauth.enabled:false}") boolean oauthEnabled,
            @Value("${matrix-prp.mcp.write-enabled:false}") boolean writeEnabled) throws IOException {
        if (!TEST_RESOURCE.equals(resource) || !oauthEnabled || !writeEnabled) return List.of();
        String mime = McpWellnessApprovalUiConfiguration.MIME;
        String html;
        try (var input = new ClassPathResource("mcp/task-create-approval.html").getInputStream()) {
            html = new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }
        var app = McpSchema.Resource.builder()
            .uri(RESOURCE_URI)
            .name("PRP task creation approval")
            .mimeType(mime)
            .build();
        return List.of(new McpStatelessServerFeatures.SyncResourceSpecification(app,
            (context, request) -> new McpSchema.ReadResourceResult(
                List.of(new McpSchema.TextResourceContents(RESOURCE_URI, mime, html)))));
    }
}
