package com.matrix.prp.mcp;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.practice.PracticeModels.*;
import com.matrix.prp.practice.PracticeService;
import com.matrix.prp.records.service.RecordService;
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
    "matrix-prp.mcp.oauth.advertised-scopes=prp.practice.read",
    "spring.ai.mcp.server.enabled=true"
})
class McpPracticeReadOAuthTests {
    static final String CLIENT="https://chatgpt.com/oauth/client.json";
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @MockitoBean UserStore users;
    @MockitoBean JdbcTemplate jdbc;
    @MockitoBean McpClientGrantService grants;
    @MockitoBean McpIdentityLinkService links;
    @MockitoBean PracticeService practice;
    @MockitoBean TaskService tasks;
    @MockitoBean RecordService records;
    @MockitoBean WellnessService wellness;
    @MockitoBean(name="mcpJwtDecoder") JwtDecoder decoder;

    void identity(long owner,String client,String scopes) {
        var jwt=Jwt.withTokenValue("practice-read-token").header("alg","RS256")
            .issuer("https://issuer.example.test").subject("practice-read-user")
            .audience(List.of("https://micor.top/api/mcp"))
            .issuedAt(Instant.now().minusSeconds(5)).expiresAt(Instant.now().plusSeconds(300))
            .claim("client_id",client).claim("scope",scopes).build();
        when(decoder.decode("practice-read-token")).thenReturn(jwt);
        when(links.resolveUserId("https://issuer.example.test","practice-read-user"))
            .thenReturn(OptionalLong.of(owner));
        when(users.findById(owner)).thenReturn(Optional.of(new UserAccount(owner,
            "synthetic","Synthetic","unused-hash",false,true)));
        when(grants.grantedScopes(owner,client)).thenReturn(Set.of("prp.practice.read"));
    }
    @BeforeEach void setup(){identity(2,CLIENT,"prp.practice.read");}
    MvcResult rpc(String tool,Map<String,Object> args) throws Exception {
        var body=new LinkedHashMap<String,Object>();
        body.put("jsonrpc","2.0"); body.put("id",1);
        body.put("method",tool==null?"tools/list":"tools/call");
        if(tool!=null)body.put("params",Map.of("name",tool,"arguments",args));
        var result=mvc.perform(post("/api/mcp").header("Authorization","Bearer practice-read-token")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON,MediaType.TEXT_EVENT_STREAM)
            .content(json.writeValueAsString(body))).andReturn();
        if(result.getRequest().isAsyncStarted())result=mvc.perform(asyncDispatch(result)).andReturn();
        return result;
    }
    @Test void manifestExposesExactlyFiveReadOnlyPracticeTools() throws Exception {
        var r=rpc(null,Map.of());
        assertThat(r.getResponse().getStatus()).isEqualTo(200);
        var tools=json.readTree(r.getResponse().getContentAsString()).path("result").path("tools");
        assertThat(tools.size()).isEqualTo(5);
        var names=new HashSet<String>();
        for(var t:tools){
            names.add(t.path("name").asText());
            assertThat(t.path("annotations").path("readOnlyHint").asBoolean()).isTrue();
            assertThat(t.path("_meta").path("securitySchemes").get(0)
                .path("scopes").get(0).asText()).isEqualTo("prp.practice.read");
        }
        assertThat(names).containsExactlyInAnyOrder("prp_practice_subjects","prp_practice_banks",
            "prp_practice_questions","prp_practice_wrong_questions","prp_practice_statistics");
    }
    @Test void ownerScopedSubjectsAndBanksReusePracticeService() throws Exception {
        when(practice.subjectsLimited(50)).thenReturn(List.of(new Subject(7L,null,"Kingdee Intermediate","synthetic")));
        when(practice.banksLimited(7L,30)).thenReturn(List.of(new Bank(9L,7L,"Intermediate Quiz","",
            "owned","private","published")));
        assertThat(rpc("prp_practice_subjects",Map.of()).getResponse().getContentAsString())
            .contains("Kingdee Intermediate");
        assertThat(rpc("prp_practice_banks",Map.of("subjectId",7)).getResponse().getContentAsString())
            .contains("Intermediate Quiz");
        verify(practice).subjectsLimited(50);
        verify(practice).banksLimited(7L,30);
        verifyNoInteractions(records,tasks,wellness);
    }
    @Test void questionsAndWrongQuestionsDoNotLeakAnswerKeysOrOversizedText() throws Exception {
        String stem="Q".repeat(850)+"PRIVATE_TRAILING_STEM";
        String option="A".repeat(205)+"PRIVATE_TRAILING_OPTION";
        var question=new QuestionPublic(9L,7L,"single",stem,
            List.of(new Option("A",option),new Option("B","other")),"hard");
        when(practice.playableLimited(7L,3)).thenReturn(List.of(question));
        when(practice.wrongQuestionsLimited(2)).thenReturn(List.of(question));
        for(var result:List.of(
            rpc("prp_practice_questions",Map.of("bankId",7,"limit",3)),
            rpc("prp_practice_wrong_questions",Map.of("limit",2)))) {
            var body=result.getResponse().getContentAsString();
            assertThat(result.getResponse().getStatus()).isEqualTo(200);
            assertThat(body).contains("truncated","true","hard")
                .doesNotContain("PRIVATE_TRAILING_STEM","PRIVATE_TRAILING_OPTION","correctAnswers","explanation");
        }
        verify(practice).playableLimited(7L,3);
        verify(practice).wrongQuestionsLimited(2);
    }
    @Test void statisticsAreReadOnlyAndOwnerScoped() throws Exception {
        when(practice.statistics()).thenReturn(new Statistics(15,10,5));
        var r=rpc("prp_practice_statistics",Map.of());
        assertThat(r.getResponse().getStatus()).isEqualTo(200);
        assertThat(r.getResponse().getContentAsString()).contains("attempted","correct","wrong","15","10");
        verify(practice).statistics();
    }
    @Test void invalidIdsAndLimitsAreRejectedBeforeCallingService() throws Exception {
        for(var entry:List.<Map.Entry<String,Map<String,Object>>>of(
            Map.entry("prp_practice_banks",Map.of("subjectId",0)),
            Map.entry("prp_practice_questions",Map.of("bankId",-1)),
            Map.entry("prp_practice_questions",Map.of("bankId",4,"limit",11)),
            Map.entry("prp_practice_wrong_questions",Map.of("limit",0)))) {
            assertThat(rpc(entry.getKey(),entry.getValue()).getResponse().getContentAsString())
                .contains("\"isError\":true");
        }
        verifyNoInteractions(practice);
    }
    @Test void missingPracticeScopeAndRevokedGrantCannotRead() throws Exception {
        identity(2,CLIENT,"prp.tasks.read");
        var r=rpc("prp_practice_statistics",Map.of());
        assertThat(r.getResponse().getContentAsString()).contains("insufficient_scope","prp.practice.read");
        verifyNoInteractions(practice);
        identity(2,CLIENT,"prp.practice.read");
        when(grants.grantedScopes(2,CLIENT)).thenReturn(Set.of());
        assertThat(rpc("prp_practice_statistics",Map.of()).getResponse().getStatus()).isEqualTo(401);
        verifyNoInteractions(practice);
    }
    @Test void otherOwnerOrUnreviewedClientCannotReadPracticeData() throws Exception {
        identity(3,CLIENT,"prp.practice.read");
        rpc("prp_practice_statistics",Map.of());
        identity(2,"unknown-client","prp.practice.read");
        rpc("prp_practice_statistics",Map.of());
        verifyNoInteractions(practice);
    }
}
