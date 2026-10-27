package com.matrix.prp.mcp;

import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.tasks.model.CreateTaskRequest;
import com.matrix.prp.tasks.model.TaskItem;
import com.matrix.prp.tasks.service.TaskService;
import com.matrix.prp.wellness.WellnessService;
import java.time.Instant;
import java.util.List;
import java.util.OptionalLong;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Real Spring Security -> MCP transport -> task repository isolation. Only the
 * OAuth JWT decoder, consent records and identity link database are mocked;
 * task reads use the actual test-profile owner-scoped repository. Separate
 * cryptographic signature/JWKS tests prove the decoder's production contract.
 */
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
class McpOAuthTaskIsolationTests {
    private static final String ISSUER = "https://issuer.example.test";
    private static final String RESOURCE = "https://micor.top/api/mcp";
    private static final String CLIENT = "https://chatgpt.com/oauth/client.json";

    @Autowired MockMvc mvc;
    @Autowired UserStore users;
    @Autowired TaskService tasks;
    @Autowired PasswordEncoder passwordEncoder;
    @MockitoBean JdbcTemplate jdbc;
    @MockitoBean McpClientGrantService clientGrants;
    @MockitoBean McpIdentityLinkService identityLinks;
    @MockitoBean WellnessService wellness;
    @MockitoBean(name = "mcpJwtDecoder") JwtDecoder oauthDecoder;

    private Jwt accessToken(String token, String subject, long forgedUserId) {
        return Jwt.withTokenValue(token)
            .header("alg", "RS256")
            .issuer(ISSUER)
            .subject(subject)
            .audience(List.of(RESOURCE))
            .issuedAt(Instant.now().minusSeconds(5))
            .expiresAt(Instant.now().plusSeconds(300))
            .claim("client_id", CLIENT)
            // A model/client-supplied owner claim is NEVER authoritative.
            .claim("prp_user_id", forgedUserId)
            .claim("scope", "prp.tasks.read")
            .build();
    }

    private String call(String bearer, String tool, String arguments, int id)
            throws Exception {
        String rpc = "{\"jsonrpc\":\"2.0\",\"id\":" + id
            + ",\"method\":\"tools/call\",\"params\":{\"name\":\""
            + tool + "\",\"arguments\":" + arguments + "}}";
        return mvc.perform(post("/api/mcp")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + bearer)
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON, MediaType.TEXT_EVENT_STREAM)
                .content(rpc))
            .andExpect(status().isOk())
            .andReturn().getResponse().getContentAsString();
    }

    private TaskItem createFor(UserAccount owner, String title) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(owner.profile(), null, List.of()));
        try {
            return tasks.create(new CreateTaskRequest(
                "work", title, "synthetic task", "low", null));
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    @Test
    void signedSubjectMappingOverridesForgedUserIdAndCannotReadOtherOwnersTasks()
            throws Exception {
        UserAccount ownerOne = users.findByUsername("admin").orElseThrow();
        String otherName = "mcp-owner-" + UUID.randomUUID();
        UserAccount ownerTwo = users.create(
            otherName, "Synthetic second owner", passwordEncoder.encode("ci-only"),
            false);
        String oneMarker = "tenant-one-" + UUID.randomUUID();
        String twoMarker = "tenant-two-" + UUID.randomUUID();
        TaskItem first = createFor(ownerOne, oneMarker);
        TaskItem second = createFor(ownerTwo, twoMarker);

        when(identityLinks.resolveUserId(ISSUER, "oauth-sub-one"))
            .thenReturn(OptionalLong.of(ownerOne.id()));
        when(identityLinks.resolveUserId(ISSUER, "oauth-sub-two"))
            .thenReturn(OptionalLong.of(ownerTwo.id()));
        when(clientGrants.grantedScopes(ownerOne.id(), CLIENT))
            .thenReturn(Set.of("prp.tasks.read"));
        when(clientGrants.grantedScopes(ownerTwo.id(), CLIENT))
            .thenReturn(Set.of("prp.tasks.read"));
        when(oauthDecoder.decode("owner-one"))
            .thenReturn(accessToken("owner-one", "oauth-sub-one", ownerTwo.id()));
        when(oauthDecoder.decode("owner-two"))
            .thenReturn(accessToken("owner-two", "oauth-sub-two", ownerOne.id()));

        String firstList = call("owner-one", "prp_tasks_list", "{}", 101);
        assertThat(firstList).contains(oneMarker).doesNotContain(twoMarker);
        String secondList = call("owner-two", "prp_tasks_list", "{}", 102);
        assertThat(secondList).contains(twoMarker).doesNotContain(oneMarker);

        String crossGet = call("owner-one", "prp_task_get",
            "{\"taskId\":" + second.id() + "}", 103);
        assertThat(crossGet).contains("\"isError\":true").doesNotContain(twoMarker);
        String ownGet = call("owner-one", "prp_task_get",
            "{\"taskId\":" + first.id() + "}", 104);
        assertThat(ownGet).contains(oneMarker).doesNotContain("\"isError\":true");

        verify(identityLinks, atLeastOnce()).resolveUserId(ISSUER, "oauth-sub-one");
        verify(identityLinks, atLeastOnce()).resolveUserId(ISSUER, "oauth-sub-two");
    }

    @Test
    void revokedOwnerGrantRejectsTheNextActualToolCall() throws Exception {
        UserAccount owner = users.findByUsername("admin").orElseThrow();
        String marker = "revocation-" + UUID.randomUUID();
        createFor(owner, marker);
        when(identityLinks.resolveUserId(ISSUER, "oauth-sub-revoked"))
            .thenReturn(OptionalLong.of(owner.id()));
        when(oauthDecoder.decode("revocable"))
            .thenReturn(accessToken("revocable", "oauth-sub-revoked", owner.id()));
        when(clientGrants.grantedScopes(owner.id(), CLIENT))
            .thenReturn(Set.of("prp.tasks.read"), Set.of());

        String before = call("revocable", "prp_tasks_list", "{}", 201);
        assertThat(before).contains(marker);
        String rpc = "{\"jsonrpc\":\"2.0\",\"id\":202,\"method\":\"tools/call\","
            + "\"params\":{\"name\":\"prp_tasks_list\",\"arguments\":{}}}";
        String after = mvc.perform(post("/api/mcp")
                .header(HttpHeaders.AUTHORIZATION, "Bearer revocable")
                .contentType(MediaType.APPLICATION_JSON)
                .content(rpc))
            .andExpect(status().isUnauthorized())
            .andReturn().getResponse().getContentAsString();
        assertThat(after).doesNotContain(marker);
        verify(clientGrants, times(2)).grantedScopes(owner.id(), CLIENT);
    }

    @Test
    void tokenScopeWithoutMatchingPrpConsentCannotReadTaskData() throws Exception {
        UserAccount owner = users.findByUsername("admin").orElseThrow();
        String marker = "scope-denied-" + UUID.randomUUID();
        createFor(owner, marker);
        when(identityLinks.resolveUserId(ISSUER, "oauth-sub-scope"))
            .thenReturn(OptionalLong.of(owner.id()));
        when(oauthDecoder.decode("scope-mismatch"))
            .thenReturn(accessToken("scope-mismatch", "oauth-sub-scope", owner.id()));
        // Grant exists for a different permission, so the OAuth bearer can
        // authenticate but the per-tool task permission must fail closed.
        when(clientGrants.grantedScopes(owner.id(), CLIENT))
            .thenReturn(Set.of("prp.finance.read"));

        String reply = call("scope-mismatch", "prp_tasks_list", "{}", 301);
        assertThat(reply).contains("\"isError\":true").doesNotContain(marker);
        verify(clientGrants).grantedScopes(owner.id(), CLIENT);
    }
}
