package com.matrix.prp.mcp;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.wellness.WellnessService;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.OptionalLong;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.MockMvcPrint;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;

/** Verify real OAuth-protected MCP resources/read in the embedded-UI opt-in profile. */
@SpringBootTest
@AutoConfigureMockMvc(print=MockMvcPrint.NONE)
@ActiveProfiles("test")
@TestPropertySource(properties={
 "matrix-prp.mcp.enabled=true",
 "matrix-prp.mcp.write-enabled=true",
 "matrix-prp.mcp.chatgpt-health-approval-ui-enabled=true",
 "matrix-prp.mcp.oauth.enabled=true",
 "matrix-prp.mcp.expanded-user-ids=2",
 "matrix-prp.mcp.oauth.issuer=https://issuer.example.test",
 "matrix-prp.mcp.oauth.jwk-set-uri=https://issuer.example.test/jwks.json",
 "matrix-prp.mcp.oauth.resource=https://micor.top/api/mcp",
 "matrix-prp.mcp.oauth.advertised-scopes=prp.wellness.read,prp.wellness.write.create,prp.wellness.write.update,prp.wellness.write.delete,prp.wellness.write.status,prp.wellness.write.confirm",
 "spring.ai.mcp.server.enabled=true"
})
class McpWellnessAppResourceHttpTests {
    private static final String CLIENT = "https://chatgpt.com/oauth/client.json";
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @MockitoBean UserStore users;
    @MockitoBean JdbcTemplate db;
    @MockitoBean McpClientGrantService grants;
    @MockitoBean McpIdentityLinkService links;
    @MockitoBean WellnessService wellness;
    @MockitoBean(name="mcpJwtDecoder") JwtDecoder decoder;

    @BeforeEach void identity() {
        String scopes = String.join(" ", McpProductionWellnessGuard.SCOPES);
        var jwt = Jwt.withTokenValue("ui-synthetic-token")
            .header("alg", "RS256")
            .issuer("https://issuer.example.test")
            .subject("synthetic-ui-owner")
            .audience(List.of("https://micor.top/api/mcp"))
            .issuedAt(Instant.now().minusSeconds(5))
            .expiresAt(Instant.now().plusSeconds(300))
            .claim("client_id", CLIENT)
            .claim("scope", scopes)
            .build();
        when(decoder.decode("ui-synthetic-token")).thenReturn(jwt);
        when(links.resolveUserId("https://issuer.example.test", "synthetic-ui-owner"))
            .thenReturn(OptionalLong.of(2L));
        when(users.findById(2L)).thenReturn(
            java.util.Optional.of(new UserAccount(2L, "synthetic", "Synthetic", "unused", false, true)));
        when(grants.grantedScopes(2L, CLIENT)).thenReturn(McpProductionWellnessGuard.SCOPES);
    }

    private MvcResult rpc(String method, Map<String,Object> params) throws Exception {
        var body = new java.util.LinkedHashMap<String,Object>();
        body.put("jsonrpc","2.0"); body.put("id",1); body.put("method",method);
        if (params != null) body.put("params", params);
        var result = mvc.perform(post("/api/mcp")
            .header("Authorization","Bearer ui-synthetic-token")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON, MediaType.TEXT_EVENT_STREAM)
            .content(json.writeValueAsString(body))).andReturn();
        if(result.getRequest().isAsyncStarted())
            result = mvc.perform(asyncDispatch(result)).andReturn();
        return result;
    }

    @Test void hostCanReadActualApprovalHtmlResourceFromSameAuthenticatedEndpoint() throws Exception {
        var result = rpc("resources/read", Map.of("uri",
            McpWellnessApprovalUiConfiguration.RESOURCE_URI));
        assertThat(result.getResponse().getStatus()).isEqualTo(200);
        var response = json.readTree(result.getResponse().getContentAsString());
        assertThat(response.path("error").isMissingNode()).isTrue();
        var contents = response.path("result").path("contents");
        assertThat(contents.isArray()).isTrue();
        assertThat(contents.get(0).path("uri").asText())
            .isEqualTo(McpWellnessApprovalUiConfiguration.RESOURCE_URI);
        assertThat(contents.get(0).path("mimeType").asText())
            .isEqualTo(McpWellnessApprovalUiConfiguration.MIME);
        assertThat(contents.get(0).path("text").asText())
            .contains("审批并保存","ui/initialize","prp_chatgpt_wellness_approval");
    }

    @Test void onlyUiMarkedApprovalIsAddedToTheHealthToolManifest() throws Exception {
        var response = json.readTree(rpc("tools/list",null).getResponse().getContentAsString());
        var tools = response.path("result").path("tools");
        assertThat(tools.size()).isEqualTo(10);
        var approval = java.util.stream.StreamSupport.stream(tools.spliterator(), false)
            .filter(t -> "prp_chatgpt_wellness_approval".equals(t.path("name").asText()))
            .findFirst().orElseThrow();
        var visibility = approval.path("_meta").path("ui").path("visibility");
        assertThat(visibility.isArray()).isTrue();
        assertThat(visibility.size()).isEqualTo(1);
        assertThat(visibility.get(0).asText()).isEqualTo("app");
        var create = java.util.stream.StreamSupport.stream(tools.spliterator(), false)
            .filter(t -> "prp_prepare_wellness_create".equals(t.path("name").asText()))
            .findFirst().orElseThrow();
        assertThat(create.path("_meta").path("ui").path("resourceUri").asText())
            .isEqualTo(McpWellnessApprovalUiConfiguration.RESOURCE_URI);
    }
}
