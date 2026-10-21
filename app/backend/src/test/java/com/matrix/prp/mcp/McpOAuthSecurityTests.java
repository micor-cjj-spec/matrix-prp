package com.matrix.prp.mcp;

import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.auth.service.JwtService;
import com.matrix.prp.wellness.WellnessService;
import java.time.Instant;
import java.util.List;
import java.util.OptionalLong;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** OAuth-only MCP chain integration. The verifier itself uses a controlled decoder in this suite. */
@SpringBootTest
@AutoConfigureMockMvc(print = org.springframework.boot.test.autoconfigure.web.servlet.MockMvcPrint.NONE)
@ActiveProfiles("test")
@TestPropertySource(properties = {
    "matrix-prp.mcp.enabled=true",
    "matrix-prp.mcp.write-enabled=false",
    "matrix-prp.mcp.oauth.enabled=true",
    "matrix-prp.mcp.oauth.issuer=https://issuer.example.test",
    "matrix-prp.mcp.oauth.jwk-set-uri=https://issuer.example.test/jwks.json",
    "matrix-prp.mcp.oauth.resource=https://micor.top/api/mcp",
    "spring.ai.mcp.server.enabled=true"
})
class McpOAuthSecurityTests {
    @Autowired MockMvc mvc;
    @Autowired UserStore users;
    @Autowired JwtService prpJwt;
    @MockitoBean JdbcTemplate jdbc;
    @MockitoBean McpClientGrantService clientGrants;
    @MockitoBean McpIdentityLinkService identityLinks;
    @MockitoBean WellnessService wellness;
    @MockitoBean(name = "mcpJwtDecoder") JwtDecoder oauthDecoder;

    private Jwt jwt(String value, String scopes, long userId) {
        return Jwt.withTokenValue(value)
            .header("alg", "RS256")
            .issuer("https://issuer.example.test")
            .subject("external-provider-subject")
            .audience(List.of("https://micor.top/api/mcp"))
            .issuedAt(Instant.now().minusSeconds(5))
            .expiresAt(Instant.now().plusSeconds(300))
            .claim("prp_user_id", userId)
            .claim("client_id", "test-client")
            .claim("scope", scopes)
            .build();
    }

    private MockHttpServletRequestBuilder mcp(String token, String body) {
        return post("/api/mcp")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON, MediaType.TEXT_EVENT_STREAM)
            .content(body);
    }

    @Test
    void resourceDiscoveryIsPublicAndNamesTheExactIssuerAndResource() throws Exception {
        mvc.perform(get("/.well-known/oauth-protected-resource/api/mcp"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.resource").value("https://micor.top/api/mcp"))
            .andExpect(jsonPath("$.authorization_servers[0]").value("https://issuer.example.test"))
            .andExpect(jsonPath("$.scopes_supported[0]").value("prp.tasks.read"));
        mvc.perform(get("/.well-known/oauth-protected-resource/another"))
            .andExpect(status().isNotFound());
    }

    @Test
    void oauthChallengeDoesNotAcceptPrpSessionJwt() throws Exception {
        var response = mvc.perform(post("/api/mcp")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\"}"))
            .andExpect(status().isUnauthorized()).andReturn().getResponse();
        assertThat(response.getHeader(HttpHeaders.WWW_AUTHENTICATE))
            .contains("resource_metadata=\"https://micor.top/.well-known/oauth-protected-resource/api/mcp\"");

        String oldPrpToken = prpJwt.issueToken(users.findByUsername("admin").orElseThrow().profile());
        when(oauthDecoder.decode(oldPrpToken)).thenThrow(new BadJwtException("Not a scoped OAuth token"));
        mvc.perform(mcp(oldPrpToken, "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/list\"}"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void oauthTaskReadDoesNotAuthorizeFinanceOrDraftWrites() throws Exception {
        when(identityLinks.resolveUserId("https://issuer.example.test", "external-provider-subject")).thenReturn(OptionalLong.of(1L));
        when(clientGrants.grantedScopes(1L, "test-client")).thenReturn(Set.of("prp.tasks.read"));
        when(oauthDecoder.decode("read-only")).thenReturn(jwt("read-only", "prp.tasks.read", 1L));
        var list = mvc.perform(mcp("read-only",
            "{\"jsonrpc\":\"2.0\",\"id\":10,\"method\":\"tools/list\",\"params\":{}}"))
            .andExpect(status().isOk()).andReturn();
        assertThat(list.getResponse().getContentAsString()).contains("prp_tasks_list");

        var task = mvc.perform(mcp("read-only",
            "{\"jsonrpc\":\"2.0\",\"id\":11,\"method\":\"tools/call\",\"params\":{\"name\":\"prp_tasks_list\",\"arguments\":{}}}"))
            .andExpect(status().isOk()).andReturn();
        assertThat(task.getResponse().getContentAsString()).contains("\"result\"")
            .doesNotContain("\"isError\":true");

        var finance = mvc.perform(mcp("read-only",
            "{\"jsonrpc\":\"2.0\",\"id\":12,\"method\":\"tools/call\",\"params\":{\"name\":\"prp_finance_month\",\"arguments\":{}}}"))
            .andExpect(status().isOk()).andReturn();
        assertThat(finance.getResponse().getContentAsString()).contains("\"isError\":true");

        var write = mvc.perform(mcp("read-only",
            "{\"jsonrpc\":\"2.0\",\"id\":13,\"method\":\"tools/call\",\"params\":{\"name\":\"prp_prepare_task\",\"arguments\":{\"moduleCode\":\"work\",\"title\":\"Forbidden\"}}}"))
            .andExpect(status().isOk()).andReturn();
        assertThat(write.getResponse().getContentAsString()).contains("\"isError\":true");
        verifyNoInteractions(jdbc);
    }

    @Test
    void revokedClientFailsOnNextAuthenticationEvenWithUnexpiredToken() throws Exception {
        when(oauthDecoder.decode("revoked-token")).thenReturn(jwt("revoked-token", "prp.tasks.read", 1L));
        when(identityLinks.resolveUserId("https://issuer.example.test", "external-provider-subject")).thenReturn(OptionalLong.of(1L));
        when(clientGrants.grantedScopes(1L, "test-client"))
            .thenReturn(Set.of("prp.tasks.read")).thenReturn(Set.of());
        mvc.perform(mcp("revoked-token",
            """
                {"jsonrpc":"2.0","id":40,"method":"tools/list"}
                """))
            .andExpect(status().isOk());
        mvc.perform(mcp("revoked-token",
            """
                {"jsonrpc":"2.0","id":41,"method":"tools/list"}
                """))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validOAuthBearerCanCompleteExplicitLinkWithoutExistingPrpMapping() throws Exception {
        when(oauthDecoder.decode("bootstrap")).thenReturn(jwt("bootstrap", "prp.tasks.read", 1L));
        when(identityLinks.complete(
            "1234567890123456789012345678901234567890123",
            "https://issuer.example.test", "external-provider-subject", "test-client"))
            .thenReturn(new McpIdentityLinkService.Link(
                "https://issuer.example.test", "external-provider-subject", true));
        mvc.perform(post("/api/mcp/link")
            .header(HttpHeaders.AUTHORIZATION, "Bearer bootstrap")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {"ticket":"1234567890123456789012345678901234567890123"}
                """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.newlyLinked").value(true));
    }

    @Test
    void oauthTokenWithoutPrpUserBindingFailsClosed() throws Exception {
        when(oauthDecoder.decode("wrong-user")).thenReturn(jwt("wrong-user", "prp.tasks.read", 999999L));
        mvc.perform(mcp("wrong-user", "{\"jsonrpc\":\"2.0\",\"id\":4,\"method\":\"tools/list\"}"))
            .andExpect(status().isUnauthorized());
    }
}
