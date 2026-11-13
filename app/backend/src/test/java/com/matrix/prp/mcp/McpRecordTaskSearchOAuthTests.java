package com.matrix.prp.mcp;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.records.model.RecordFilter;
import com.matrix.prp.records.model.RecordItem;
import com.matrix.prp.records.service.RecordService;
import com.matrix.prp.tasks.model.TaskFilter;
import com.matrix.prp.tasks.model.TaskItem;
import com.matrix.prp.tasks.service.TaskService;
import com.matrix.prp.wellness.WellnessService;
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
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

/** Exercise new searches via verified OAuth MCP HTTP tools/list and tools/call. */
@SpringBootTest
@AutoConfigureMockMvc(print=MockMvcPrint.NONE)
@ActiveProfiles("test")
@TestPropertySource(properties={
    "matrix-prp.mcp.enabled=true",
    "matrix-prp.mcp.write-enabled=false",
    "matrix-prp.mcp.additional-read-tools-enabled=true",
    "matrix-prp.mcp.oauth.enabled=true",
    "matrix-prp.mcp.expanded-user-ids=2",
    "matrix-prp.mcp.oauth.issuer=https://issuer.example.test",
    "matrix-prp.mcp.oauth.jwk-set-uri=https://issuer.example.test/jwks.json",
    "matrix-prp.mcp.oauth.resource=https://micor.top/api/mcp",
    "matrix-prp.mcp.oauth.advertised-scopes=prp.tasks.read,prp.records.read",
    "spring.ai.mcp.server.enabled=true"
})
class McpRecordTaskSearchOAuthTests {
    static final String CLIENT="https://chatgpt.com/oauth/client.json";
    static final Set<String> READ=Set.of("prp.tasks.read","prp.records.read");
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @MockitoBean UserStore users;
    @MockitoBean JdbcTemplate db;
    @MockitoBean McpClientGrantService grants;
    @MockitoBean McpIdentityLinkService links;
    @MockitoBean TaskService tasks;
    @MockitoBean RecordService records;
    @MockitoBean WellnessService wellness;
    @MockitoBean(name="mcpJwtDecoder") JwtDecoder decoder;

    void identity(long owner,String client,String scope) {
        var jwt=Jwt.withTokenValue("record-read-test").header("alg","RS256")
            .issuer("https://issuer.example.test").subject("record-read-sub")
            .audience(List.of("https://micor.top/api/mcp"))
            .issuedAt(Instant.now().minusSeconds(5)).expiresAt(Instant.now().plusSeconds(300))
            .claim("client_id",client).claim("scope",scope).build();
        when(decoder.decode("record-read-test")).thenReturn(jwt);
        when(links.resolveUserId("https://issuer.example.test","record-read-sub")).thenReturn(OptionalLong.of(owner));
        when(users.findById(owner)).thenReturn(Optional.of(
            new UserAccount(owner,"synthetic","Synthetic","unused",false,true)));
        when(grants.grantedScopes(owner,client)).thenReturn(READ);
    }
    @BeforeEach void setup() { identity(2,CLIENT,"prp.tasks.read prp.records.read"); }

    MvcResult rpc(String name,Map<String,Object> args) throws Exception {
        var body=new LinkedHashMap<String,Object>();
        body.put("jsonrpc","2.0");body.put("id",1);
        body.put("method",name==null?"tools/list":"tools/call");
        if(name!=null)body.put("params",Map.of("name",name,"arguments",args));
        var r=mvc.perform(post("/api/mcp").header("Authorization","Bearer record-read-test")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON,MediaType.TEXT_EVENT_STREAM)
            .content(json.writeValueAsString(body))).andReturn();
        if(r.getRequest().isAsyncStarted())r=mvc.perform(asyncDispatch(r)).andReturn();
        return r;
    }

    @Test void toolsListContainsSearchesOnlyWithTheirReadScopes() throws Exception {
        var response=rpc(null,Map.of());
        assertThat(response.getResponse().getStatus()).isEqualTo(200);
        var tools=json.readTree(response.getResponse().getContentAsString()).path("result").path("tools");
        Set<String> names=new HashSet<>();
        for(var tool:tools) {
            names.add(tool.path("name").asText());
            String scope=tool.path("_meta").path("securitySchemes").get(0)
                .path("scopes").get(0).asText();
            assertThat(READ).contains(scope);
            assertThat(tool.path("annotations").path("readOnlyHint").asBoolean()).isTrue();
        }
        assertThat(names).contains("prp_tasks_search","prp_records_search","prp_task_get",
            "prp_tasks_list","prp_tasks_summary").doesNotContain("prp_wellness_goals","prp_prepare_record");
        assertThat(names).hasSize(5);
    }

    @Test void taskSearchForwardsEveryValidatedFilterToExistingService() throws Exception {
        when(tasks.listLimited(any(TaskFilter.class),eq(7))).thenReturn(List.of());
        var r=rpc("prp_tasks_search",Map.of("status","in_progress","moduleCode","work",
            "priority","high","dueDate","2026-11-15","limit",7));
        assertThat(r.getResponse().getStatus()).isEqualTo(200);
        assertThat(r.getResponse().getContentAsString()).contains("\"isError\":false");
        verify(tasks).listLimited(new TaskFilter("in_progress","work",
            LocalDate.of(2026,11,15),"high"),7);
        verifyNoInteractions(records);
    }

    @Test void taskSearchRejectsInvalidFiltersBeforeDatabase() throws Exception {
        for(var request:List.<Map<String,Object>>of(
            Map.of("status","superadmin"),
            Map.of("priority","critical"),
            Map.of("moduleCode","a space"),
            Map.of("dueDate","2026-02-30"),
            Map.of("limit",51),
            Map.of("limit",0))) {
            var r=rpc("prp_tasks_search",request);
            assertThat(r.getResponse().getContentAsString()).contains("\"isError\":true");
        }
        verifyNoInteractions(tasks,records);
    }

    @Test void recordSearchLimitsQueryAndTruncatesPrivateText() throws Exception {
        String body="x".repeat(500)+"PRIVATE_TAIL";
        when(records.listLimited(any(RecordFilter.class),eq(20))).thenReturn(List.of(
            new RecordItem(123,"life","Synthetic journal",body,LocalDate.of(2026,11,12),
                OffsetDateTime.parse("2026-11-12T18:00:00+08:00"),List.of())));
        var r=rpc("prp_records_search",Map.of("moduleCode","life","tagId",5,
            "recordDate","2026-11-12","keyword","journal"));
        assertThat(r.getResponse().getStatus()).isEqualTo(200);
        assertThat(r.getResponse().getContentAsString()).contains("Synthetic journal","123")
            .doesNotContain("PRIVATE_TAIL");
        verify(records).listLimited(new RecordFilter("life",5L,LocalDate.of(2026,11,12),"journal"),20);
        verifyNoInteractions(tasks);
    }

    @Test void recordSearchRejectsInvalidFiltersBeforeDatabase() throws Exception {
        for(var request:List.<Map<String,Object>>of(
            Map.of("tagId",-1),
            Map.of("moduleCode","with spaces"),
            Map.of("keyword","x".repeat(101)),
            Map.of("recordDate","invalid"))) {
            var r=rpc("prp_records_search",request);
            assertThat(r.getResponse().getContentAsString()).contains("\"isError\":true");
        }
        verifyNoInteractions(tasks,records);
    }

    @Test void missingRecordsScopeRequiresExplicitOAuthConsent() throws Exception {
        identity(2,CLIENT,"prp.tasks.read");
        var denied=rpc("prp_records_search",Map.of());
        assertThat(denied.getResponse().getContentAsString()).contains("insufficient_scope","prp.records.read");
        verifyNoInteractions(records);
    }

    @Test void revokedGrantCannotReadRecords() throws Exception {
        when(grants.grantedScopes(2,CLIENT)).thenReturn(Set.of());
        assertThat(rpc("prp_records_search",Map.of()).getResponse().getStatus()).isEqualTo(401);
        verifyNoInteractions(records);
    }

    @Test void unallowlistedOwnerAndWrongClientAreRejected() throws Exception {
        identity(3,CLIENT,"prp.tasks.read prp.records.read");
        rpc("prp_records_search",Map.of());
        identity(2,"not-chatgpt","prp.tasks.read prp.records.read");
        rpc("prp_records_search",Map.of());
        verifyNoInteractions(records);
    }
}
