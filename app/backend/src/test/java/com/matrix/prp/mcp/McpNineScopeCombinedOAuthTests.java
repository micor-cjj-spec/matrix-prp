package com.matrix.prp.mcp;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.finance.service.FinanceService;
import com.matrix.prp.practice.PracticeService;
import com.matrix.prp.records.service.RecordService;
import com.matrix.prp.tasks.model.TaskFilter;
import com.matrix.prp.tasks.service.TaskService;
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
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;

/**
 * Disposable MVC-level OAuth transport regression for the complete nine-scope profile.
 * The JWT decoder and business services are mocked. No Keycloak, database or live user
 * is accessed. Production startup guards and real Keycloak integration remain separate gates.
 */
@SpringBootTest
@AutoConfigureMockMvc(print=MockMvcPrint.NONE)
@ActiveProfiles("test")
@TestPropertySource(properties={
    "matrix-prp.mcp.enabled=true",
    "matrix-prp.mcp.write-enabled=true",
    "matrix-prp.mcp.additional-read-tools-enabled=true",
    "matrix-prp.mcp.chatgpt-health-approval-ui-enabled=true",
    "matrix-prp.mcp.oauth.enabled=true",
    "matrix-prp.mcp.expanded-user-ids=2",
    "matrix-prp.mcp.oauth.issuer=https://issuer.example.test",
    "matrix-prp.mcp.oauth.jwk-set-uri=https://issuer.example.test/jwks.json",
    "matrix-prp.mcp.oauth.resource=https://micor.top/api/mcp",
    "matrix-prp.mcp.oauth.advertised-scopes=prp.wellness.read,prp.wellness.write.create,prp.wellness.write.update,prp.wellness.write.delete,prp.wellness.write.status,prp.wellness.write.confirm,prp.tasks.read,prp.records.read,prp.practice.read",
    "spring.ai.mcp.server.enabled=true"
})
class McpNineScopeCombinedOAuthTests {
    private static final String CLIENT="https://chatgpt.com/oauth/client.json";
    private static final String ISSUER="https://issuer.example.test";
    private static final String RESOURCE="https://micor.top/api/mcp";
    private static final Set<String> NINE_SCOPES=Set.of(
        "prp.wellness.read","prp.wellness.write.create","prp.wellness.write.update",
        "prp.wellness.write.delete","prp.wellness.write.status","prp.wellness.write.confirm",
        "prp.tasks.read","prp.records.read","prp.practice.read");
    private static final Set<String> MODEL_AND_APP_TOOLS=Set.of(
        "prp_wellness_daily","prp_wellness_list","prp_wellness_get","prp_wellness_foods",
        "prp_prepare_wellness_create","prp_prepare_wellness_update",
        "prp_prepare_wellness_delete","prp_wellness_draft_status",
        "prp_confirm_wellness_draft","prp_chatgpt_wellness_approval",
        "prp_tasks_list","prp_task_get","prp_tasks_summary","prp_tasks_search",
        "prp_records_search","prp_wellness_trends","prp_wellness_goals",
        "prp_wellness_frequent_foods","prp_wellness_dishes",
        "prp_practice_subjects","prp_practice_banks","prp_practice_questions",
        "prp_practice_wrong_questions","prp_practice_statistics");

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @MockitoBean UserStore users;
    @MockitoBean JdbcTemplate db;
    @MockitoBean McpClientGrantService grants;
    @MockitoBean McpIdentityLinkService links;
    @MockitoBean TaskService tasks;
    @MockitoBean RecordService records;
    @MockitoBean WellnessService wellness;
    @MockitoBean FinanceService finance;
    @MockitoBean PracticeService practice;
    @MockitoBean(name="mcpJwtDecoder") JwtDecoder decoder;

    private void identity(long owner,String client,Set<String> tokenScopes,Set<String> grantScopes) {
        var jwt=Jwt.withTokenValue("combined-nine-scope-test")
            .header("alg","RS256").issuer(ISSUER).subject("synthetic-owner")
            .audience(List.of(RESOURCE))
            .issuedAt(Instant.now().minusSeconds(5))
            .expiresAt(Instant.now().plusSeconds(300))
            .claim("client_id",client)
            .claim("scope",String.join(" ",tokenScopes)).build();
        when(decoder.decode("combined-nine-scope-test")).thenReturn(jwt);
        when(links.resolveUserId(ISSUER,"synthetic-owner")).thenReturn(OptionalLong.of(owner));
        when(users.findById(owner)).thenReturn(Optional.of(
            new UserAccount(owner,"synthetic","Synthetic","unused",false,true)));
        when(grants.grantedScopes(owner,client)).thenReturn(grantScopes);
    }

    @BeforeEach void setUp() {
        identity(2,CLIENT,NINE_SCOPES,NINE_SCOPES);
    }

    private MvcResult rpc(String name,Map<String,Object> args) throws Exception {
        var payload=new LinkedHashMap<String,Object>();
        payload.put("jsonrpc","2.0");
        payload.put("id",1);
        payload.put("method",name==null?"tools/list":"tools/call");
        if(name!=null)payload.put("params",Map.of("name",name,"arguments",args));
        var r=mvc.perform(post("/api/mcp")
            .header("Authorization","Bearer combined-nine-scope-test")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON,MediaType.TEXT_EVENT_STREAM)
            .content(json.writeValueAsString(payload))).andReturn();
        if(r.getRequest().isAsyncStarted())r=mvc.perform(asyncDispatch(r)).andReturn();
        return r;
    }

    @Test void fullNineScopesExposeExactlyTwelveAdditionalReadsAndPreserveHealthApproval() throws Exception {
        var response=rpc(null,Map.of());
        assertThat(response.getResponse().getStatus()).isEqualTo(200);
        var manifest=json.readTree(response.getResponse().getContentAsString()).path("result").path("tools");
        assertThat(manifest.size()).isEqualTo(24);
        var names=new HashSet<String>();
        for(var tool:manifest) {
            String name=tool.path("name").asText();
            names.add(name);
            String required=tool.path("_meta").path("securitySchemes").get(0)
                .path("scopes").get(0).asText();
            assertThat(NINE_SCOPES).contains(required);
            if(Set.of("prp_tasks_search","prp_records_search","prp_practice_questions",
                      "prp_wellness_trends").contains(name)) {
                assertThat(tool.path("annotations").path("readOnlyHint").asBoolean()).isTrue();
            }
            if("prp_chatgpt_wellness_approval".equals(name)) {
                assertThat(tool.path("_meta").path("ui").path("visibility").get(0).asText())
                    .isEqualTo("app");
            }
        }
        assertThat(names).containsExactlyInAnyOrderElementsOf(MODEL_AND_APP_TOOLS);
        assertThat(names).doesNotContain("prp_prepare_task","prp_prepare_finance",
            "prp_prepare_record","prp_confirm_draft","prp_finance_month");
    }

    @Test void readOnlyTokenCanSearchTasksButCannotPrepareHealthWrite() throws Exception {
        identity(2,CLIENT,Set.of("prp.tasks.read","prp.records.read","prp.practice.read",
                                  "prp.wellness.read"),NINE_SCOPES);
        when(tasks.listLimited(any(TaskFilter.class),eq(3))).thenReturn(List.of());
        var search=rpc("prp_tasks_search",Map.of("limit",3));
        assertThat(search.getResponse().getStatus()).isEqualTo(200);
        assertThat(search.getResponse().getContentAsString()).contains("\"isError\":false");
        verify(tasks).listLimited(any(TaskFilter.class),eq(3));

        var draft=rpc("prp_prepare_wellness_create",Map.of(
            "entity","exercise","input",Map.of("exercise",Map.of(
                "performedOn","2026-11-13","name","Synthetic walk","durationMinutes",30))));
        assertThat(draft.getResponse().getStatus()).isEqualTo(200);
        assertThat(draft.getResponse().getContentAsString())
            .contains("insufficient_scope","prp.wellness.write.create");
        verifyNoInteractions(db,wellness);
    }

    @Test void RevokedGrantWrongClientAndForeignOwnerNeverReachBusinessServices() throws Exception {
        identity(2,CLIENT,NINE_SCOPES,Set.of());
        assertThat(rpc("prp_tasks_search",Map.of()).getResponse().getStatus()).isEqualTo(401);
        identity(3,CLIENT,NINE_SCOPES,NINE_SCOPES);
        rpc("prp_tasks_search",Map.of());
        identity(2,"https://unreviewed.example.test/client",NINE_SCOPES,NINE_SCOPES);
        rpc("prp_records_search",Map.of());
        verifyNoInteractions(tasks,records,practice,wellness,finance);
    }
}
