package com.matrix.prp.mcp;

import com.matrix.prp.auth.model.UserProfile;
import io.modelcontextprotocol.server.McpStatelessServerFeatures;
import io.modelcontextprotocol.spec.McpSchema;
import com.matrix.prp.auth.security.CurrentUser;
import java.util.LinkedHashMap;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import java.util.List;
import java.util.Map;
import java.util.Set;
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
    // This registry is a *second* trust boundary in addition to each
    // tool's McpScopeGuard: not-advertised capabilities cannot be
    // enumerated or invoked through the OAuth MCP transport.
    private static final Map<String, String> REQUIRED_SCOPE = Map.ofEntries(
        Map.entry("prp_tasks_list", "prp.tasks.read"),
        Map.entry("prp_task_get", "prp.tasks.read"),
        Map.entry("prp_finance_month", "prp.finance.read"),
        Map.entry("prp_wellness_daily", "prp.wellness.read"),
        Map.entry("prp_prepare_task", "prp.write.create"),
        Map.entry("prp_prepare_finance", "prp.write.create"),
        Map.entry("prp_prepare_record", "prp.write.create"),
        Map.entry("prp_prepare_meal", "prp.write.create"),
        Map.entry("prp_prepare_task_update", "prp.write.update"),
        Map.entry("prp_prepare_task_delete", "prp.write.delete"),
        Map.entry("prp_draft_status", "prp.write.status"),
        Map.entry("prp_confirm_draft", "prp.write.confirm")
    );

    static Set<String> exposedNames(String configured, boolean writeEnabled) {
        var permitted = Set.copyOf(
            McpOAuthMetadataController.parseAdvertisedScopes(configured, writeEnabled));
        return REQUIRED_SCOPE.entrySet().stream()
            .filter(entry -> permitted.contains(entry.getValue()))
            .map(Map.Entry::getKey)
            .collect(java.util.stream.Collectors.toUnmodifiableSet());
    }
    @Bean
    public List<McpStatelessServerFeatures.SyncToolSpecification> prpMcpSpecifications(
            PrpMcpTools tools, McpScopeGuard scopeGuard, org.springframework.beans.factory.ObjectProvider<McpClientGrantService> grantProvider, McpDraftService drafts,
            @Value("${matrix-prp.mcp.oauth.resource:}") String resource, @Value("${matrix-prp.mcp.oauth.enabled:false}") boolean oauthEnabled,
            @Value("${matrix-prp.mcp.oauth.advertised-scopes:prp.tasks.read}") String advertisedScopes,
            @Value("${matrix-prp.mcp.write-enabled:false}") boolean writeEnabled) {
        var definitions = new SyncStatelessMcpToolProvider(List.of(tools)).getToolSpecifications();
        var expected = java.util.Set.of("prp_tasks_list", "prp_task_get", "prp_finance_month",
            "prp_wellness_daily", "prp_prepare_task", "prp_prepare_finance", "prp_prepare_record",
            "prp_prepare_meal",
            "prp_draft_status", "prp_confirm_draft", "prp_prepare_task_update", "prp_prepare_task_delete");
        var actual = definitions.stream().map(spec -> spec.tool().name()).collect(java.util.stream.Collectors.toSet());
        if (!REQUIRED_SCOPE.keySet().equals(expected)) {
            throw new IllegalStateException("PRP MCP scope-to-tool registry mismatch");
        }
        if (definitions.size() != expected.size() || !actual.equals(expected)) {
            throw new IllegalStateException("PRP MCP tool allowlist mismatch; refusing to start");
        }
        if (!oauthEnabled) return List.copyOf(definitions); // isolated old test path only
        McpClientGrantService grants = grantProvider.getObject();
        Set<String> exposed = exposedNames(advertisedScopes, writeEnabled);
        String metadataUri = McpOAuthMetadataController.metadataUrl(
            McpOAuthResourceServerConfig.strictHttps(resource, "MCP OAuth resource"));
        return definitions.stream()
            .filter(spec -> exposed.contains(spec.tool().name()))
            .map(spec -> new McpStatelessServerFeatures.SyncToolSpecification(
            withOAuthScheme(spec.tool(), REQUIRED_SCOPE.get(spec.tool().name())),
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
                    requireCurrentScope(scopeGuard, grants, auth, REQUIRED_SCOPE.get(spec.tool().name()));
                    // Confirmation also requires the approved draft's operation scope.
                    // Check outside the SDK reflection adapter so its generic error
                    // conversion cannot discard the OAuth challenge metadata.
                    if ("prp_confirm_draft".equals(spec.tool().name()) && request.arguments() != null
                            && request.arguments().get("draftId") instanceof String draftId) {
                        var review = drafts.review(draftId);
                        String operationScope = switch (review.kind()) {
                            case "TASK_UPDATE" -> "prp.write.update";
                            case "TASK_DELETE" -> "prp.write.delete";
                            default -> "prp.write.create";
                        };
                        requireCurrentScope(scopeGuard, grants, auth, operationScope);
                    }
                    return spec.callHandler().apply(transport, request);
                } catch (McpScopeGuard.MissingScope missing) {
                    // MissingScope is emitted only for a token-scope deficit
                    // against the immutable, server-verified owner-consent snapshot.
                    return insufficientScope(metadataUri, missing.requiredScope());
                } catch (ResponseStatusException rejected) {
                    return denied();
                } finally {
                    SecurityContextHolder.setContext(oldContext);
                }
            }
        )).toList();
    }
    private static McpSchema.Tool withOAuthScheme(McpSchema.Tool tool, String requiredScope) {
        var meta = new LinkedHashMap<String, Object>();
        if (tool.meta() != null) meta.putAll(tool.meta());
        // SDK 0.18 has no top-level securitySchemes field. This is the official
        // compatibility location read by ChatGPT; preserve every existing field.
        meta.put("securitySchemes", List.of(Map.of("type", "oauth2", "scopes", List.of(requiredScope))));
        return new McpSchema.Tool(tool.name(), tool.title(), tool.description(), tool.inputSchema(),
            tool.outputSchema(), tool.annotations(), Map.copyOf(meta));
    }

    private static void requireCurrentScope(McpScopeGuard scopeGuard, McpClientGrantService grants,
                                           Authentication auth, String scope) {
        // Preserve the existing per-request read-consent contract. Writes also
        // re-check consent immediately before invocation, including confirmation.
        if (scope.startsWith("prp.write.")
                && (!(auth.getDetails() instanceof McpScopeGuard.VerifiedClient verified)
                    || !grants.grantedScopes(CurrentUser.id(), verified.clientId()).contains(scope))) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "PRP owner grant does not permit this operation");
        }
        scopeGuard.require(scope);
    }

    private static McpSchema.CallToolResult insufficientScope(String metadataUri, String scope) {
        String challenge = "Bearer resource_metadata=\"" + metadataUri
            + "\", error=\"insufficient_scope\", error_description=\"Additional PRP permission is required\", scope=\""
            + scope + "\"";
        return McpSchema.CallToolResult.builder().isError(true)
            .addTextContent("Additional OAuth permission is required: " + scope)
            .meta(Map.of("mcp/www_authenticate", List.of(challenge))).build();
    }

    private static McpSchema.CallToolResult denied() {
        return McpSchema.CallToolResult.builder().isError(true)
            .addTextContent("PRP authorization or draft validation failed").build();
    }

}
