package com.matrix.prp.mcp;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.wellness.WellnessService;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.*;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.jwt.*;
import org.springframework.test.context.*;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.*;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;

/** Actual HTTP OAuth filter, actual MCP SDK registry, verified principal and incremental challenge. */
@SpringBootTest
@AutoConfigureMockMvc(print=MockMvcPrint.NONE)
@ActiveProfiles("test")
@TestPropertySource(properties={"matrix-prp.mcp.enabled=true","matrix-prp.mcp.write-enabled=true",
 "matrix-prp.mcp.oauth.enabled=true","matrix-prp.mcp.expanded-user-ids=2",
 "matrix-prp.mcp.oauth.issuer=https://issuer.example.test",
 "matrix-prp.mcp.oauth.jwk-set-uri=https://issuer.example.test/jwks.json",
 "matrix-prp.mcp.oauth.resource=https://micor.top/api/mcp",
 "matrix-prp.mcp.oauth.advertised-scopes=prp.wellness.read,prp.wellness.write.create,prp.wellness.write.update,prp.wellness.write.delete,prp.wellness.write.status,prp.wellness.write.confirm",
 "spring.ai.mcp.server.enabled=true"})
class McpWellnessOAuthTests {
    static final String CLIENT="https://chatgpt.com/oauth/client.json";
    static final Set<String> HEALTH=McpProductionWellnessGuard.SCOPES;
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @MockitoBean UserStore users;
    @MockitoBean JdbcTemplate db;
    @MockitoBean McpClientGrantService grants;
    @MockitoBean McpIdentityLinkService links;
    @MockitoBean WellnessService wellness;
    @MockitoBean(name="mcpJwtDecoder") JwtDecoder decoder;
    void identity(long owner,String client,String scope) {
        var jwt=Jwt.withTokenValue("synthetic-health").header("alg","RS256").issuer("https://issuer.example.test")
            .subject("synthetic-health-sub").audience(List.of("https://micor.top/api/mcp"))
            .issuedAt(Instant.now().minusSeconds(5)).expiresAt(Instant.now().plusSeconds(300))
            .claim("client_id",client).claim("scope",scope).build();
        when(decoder.decode("synthetic-health")).thenReturn(jwt);
        when(links.resolveUserId("https://issuer.example.test","synthetic-health-sub")).thenReturn(OptionalLong.of(owner));
        when(users.findById(owner)).thenReturn(Optional.of(new UserAccount(owner,"synthetic","Synthetic","unused",false,true)));
        when(grants.grantedScopes(owner,client)).thenReturn(HEALTH);
    }
    @BeforeEach void setup() { identity(2,CLIENT,String.join(" ",HEALTH)); }
    MvcResult rpc(String method,String name,Map<String,Object> args) throws Exception {
        var body=new LinkedHashMap<String,Object>();body.put("jsonrpc","2.0");body.put("id",1);body.put("method",method);
        if(name!=null) body.put("params",Map.of("name",name,"arguments",args));
        var result=mvc.perform(post("/api/mcp").header("Authorization","Bearer synthetic-health")
            .contentType(MediaType.APPLICATION_JSON).accept(MediaType.APPLICATION_JSON,MediaType.TEXT_EVENT_STREAM)
            .content(json.writeValueAsString(body))).andReturn();
        if(result.getRequest().isAsyncStarted()) result=mvc.perform(asyncDispatch(result)).andReturn();return result;
    }
    Map<String,Object> exercise() { return Map.of("entity","exercise","input",Map.of("exercise",Map.of("performedOn","2026-11-05","name","Synthetic walk","durationMinutes",30))); }
    @Test void healthManifestIsExactlyNineToolsWithPerToolOAuthSchemes() throws Exception {
        var r=rpc("tools/list",null,Map.of());assertThat(r.getResponse().getStatus()).isEqualTo(200);
        var tools=json.readTree(r.getResponse().getContentAsString()).path("result").path("tools");
        assertThat(tools.size()).isEqualTo(9);
        for(var t:tools) {
            assertThat(t.path("name").asText()).contains("wellness");
            var scope=t.path("_meta").path("securitySchemes").get(0).path("scopes").get(0).asText();
            assertThat(HEALTH).contains(scope);
        }
        assertThat(r.getResponse().getContentAsString()).doesNotContain("prp_prepare_task","prp_prepare_finance","prp_prepare_record");
    }
    @Test void oldHealthReadTokenReceivesOAuthScopeChallengeWithoutDraftWrites() throws Exception {
        identity(2,CLIENT,"prp.wellness.read");
        var r=rpc("tools/call","prp_prepare_wellness_create",exercise());
        assertThat(r.getResponse().getStatus()).isEqualTo(200);
        var result=json.readTree(r.getResponse().getContentAsString()).path("result");
        assertThat(result.path("isError").asBoolean()).isTrue();
        assertThat(result.path("_meta").path("mcp/www_authenticate").toString()).contains("insufficient_scope","prp.wellness.write.create","resource_metadata");
        verifyNoInteractions(db,wellness);
    }
    @Test void matchingWriteTokenCanOnlyPrepareAnOwnerBoundDraft() throws Exception {
        when(db.queryForObject(anyString(),eq(Integer.class),eq(2L))).thenReturn(0);
        var r=rpc("tools/call","prp_prepare_wellness_create",exercise());
        assertThat(r.getResponse().getStatus()).isEqualTo(200);
        assertThat(r.getResponse().getContentAsString()).contains("draftId","WELLNESS_CREATE","prp_confirm_wellness_draft").doesNotContain("\"isError\":true");
        verify(db).update(startsWith("INSERT INTO prp_mcp_write_drafts"),any(),eq(2L),eq("WELLNESS_CREATE"),any(),any());
        verifyNoInteractions(wellness);
    }
    @Test void revokedConsentRejectsTheUnexpiredToken() throws Exception {
        when(grants.grantedScopes(2,CLIENT)).thenReturn(Set.of());
        assertThat(rpc("tools/call","prp_prepare_wellness_create",exercise()).getResponse().getStatus()).isEqualTo(401);
        verifyNoInteractions(db,wellness);
    }
    @Test void consentRemovedAfterAuthenticationStillBlocksTheWrite() throws Exception {
        when(grants.grantedScopes(2,CLIENT)).thenReturn(HEALTH,Set.of());
        var r=rpc("tools/call","prp_prepare_wellness_create",exercise());
        assertThat(r.getResponse().getContentAsString()).contains("\"isError\":true");
        verifyNoInteractions(db,wellness);
    }
    @Test @SuppressWarnings("unchecked") void confirmationRequiresTheHealthOperationScopeAndCannotConfirmATask() throws Exception {
        String id="41abc027-d67e-4bdf-8985-e3ec97d23204";
        identity(2,CLIENT,"prp.wellness.read prp.wellness.write.confirm prp.wellness.write.create");
        when(db.query(startsWith("SELECT kind,payload_json,status"),any(org.springframework.jdbc.core.RowMapper.class),eq(id),eq(2L)))
            .thenReturn(List.of(new McpDraftService.Review(id,"WELLNESS_DELETE",json.createObjectNode(),"APPROVED","2099-01-01T00:00:00")));
        var result=rpc("tools/call","prp_confirm_wellness_draft",Map.of("draftId",id));
        assertThat(result.getResponse().getContentAsString()).contains("insufficient_scope","prp.wellness.write.delete");
        when(db.query(startsWith("SELECT kind,payload_json,status"),any(org.springframework.jdbc.core.RowMapper.class),eq(id),eq(2L)))
            .thenReturn(List.of(new McpDraftService.Review(id,"TASK_DELETE",json.createObjectNode(),"APPROVED","2099-01-01T00:00:00")));
        assertThat(rpc("tools/call","prp_confirm_wellness_draft",Map.of("draftId",id)).getResponse().getContentAsString()).contains("\"isError\":true");
        verify(db,never()).update(startsWith("UPDATE prp_mcp_write_drafts SET status='CONSUMED'"),any(),any(),any());
    }
    @Test void wrongClientOrAccountCannotUseTheNewScopes() throws Exception {
        identity(2,"not-chatgpt",String.join(" ",HEALTH));rpc("tools/call","prp_prepare_wellness_create",exercise());
        identity(3,CLIENT,String.join(" ",HEALTH));rpc("tools/call","prp_prepare_wellness_create",exercise());
        verifyNoInteractions(db,wellness);
    }
}
