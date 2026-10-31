package com.matrix.prp.mcp;

import java.net.URI;
import java.util.List;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * RFC 8707 resource and RFC 9728 protected-resource metadata must agree with
 * the exact raw /api/mcp path accepted by the reviewed Nginx guard. This suite
 * does not contact an issuer, fetch keys, install a route or enable MCP.
 */
class McpOAuthCanonicalResourceTests {
    private static final String ISSUER = "https://auth-test.micor.top/realms/prp-mcp";
    private static final String JWKS = ISSUER + "/protocol/openid-connect/certs";

    private static McpOAuthResourceServerConfig resource(String url) {
        return new McpOAuthResourceServerConfig(ISSUER, JWKS, url);
    }

    @Test
    void canonicalResourceIsAcceptedAndProducesExactProtectedMetadataUrl() {
        String canonical = "https://prp-test.micor.top/api/mcp";
        assertThatCode(() -> resource(canonical)).doesNotThrowAnyException();
        assertThat(McpOAuthMetadataController.metadataUrl(canonical))
            .isEqualTo("https://prp-test.micor.top/.well-known/oauth-protected-resource/api/mcp");
    }

    @Test
    void noncanonicalRawPathsMustFailBeforeTheOAuthServerStarts() {
        List<String> aliases = List.of(
            "https://prp-test.micor.top/prefix/api/mcp",
            "https://prp-test.micor.top/api/%6dcp",
            "https://prp-test.micor.top/api/../api/mcp",
            "https://prp-test.micor.top/api/mcp/",
            "https://prp-test.micor.top//api/mcp",
            "https://prp-test.micor.top/api/mcp%2F",
            "https://prp-test.micor.top/api/mcp?probe=1",
            "https://prp-test.micor.top/api/mcp#fragment");
        for (String alias : aliases) {
            assertThatThrownBy(() -> resource(alias))
                .as("An OAuth audience must not use a path or parameter alias")
                .isInstanceOf(IllegalStateException.class);
        }
    }

    @Test
    void canonicalResourceDoesNotTurnOffStrictIssuerAndKeyValidation() {
        assertThatThrownBy(() -> new McpOAuthResourceServerConfig(
            "http://auth-test.micor.top/realms/prp-mcp",
            JWKS, "https://prp-test.micor.top/api/mcp"))
            .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> new McpOAuthResourceServerConfig(
            ISSUER, "http://auth-test.micor.top/jwks.json",
            "https://prp-test.micor.top/api/mcp"))
            .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> new McpOAuthResourceServerConfig(
            ISSUER, JWKS, "https://user:password@prp-test.micor.top/api/mcp"))
            .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void canonicalMatchingUsesRawUriRatherThanDecodedPath() {
        URI encoded = URI.create("https://prp-test.micor.top/api/%6dcp");
        assertThat(encoded.getPath()).isEqualTo("/api/mcp");
        assertThat(encoded.getRawPath()).isNotEqualTo("/api/mcp");
    }
}
