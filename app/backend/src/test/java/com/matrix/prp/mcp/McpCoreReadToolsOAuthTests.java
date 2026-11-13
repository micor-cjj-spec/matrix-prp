package com.matrix.prp.mcp;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.tasks.model.TaskSummary;
import com.matrix.prp.tasks.service.TaskService;
import com.matrix.prp.wellness.WellnessModels.*;
import com.matrix.prp.wellness.WellnessService;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.*;
import java.util.stream.IntStream;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.*;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.jwt.*;
import org.springframework.test.context.*;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.*;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;

/** Real OAuth security filter and MCP SDK transport for opt-in P2 read tools. */
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
    "matrix-prp.mcp.oauth.advertised-scopes=prp.tasks.read,prp.wellness.read",
    "spring.ai.mcp.server.enabled=true"
})
class McpCoreReadToolsOAuthTests {
    static final String CLIENT="https://chatgpt.com/oauth/client.json";
    static final Set<String> READ=Set.of("prp.tasks.read","prp.wellness.read");
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @MockitoBean UserStore users;
    @MockitoBean McpClientGrantService grants;
    @MockitoBean McpIdentityLinkService links;
    @MockitoBean TaskService tasks;
    @MockitoBean WellnessService wellness;
    @MockitoBean(name="mcpJwtDecoder") JwtDecoder decoder;

    void identity(long owner, String client, String scope) {
        var jwt=Jwt.withTokenValue("core-read-test").header("alg","RS256")
            .issuer("https://issuer.example.test").subject("core-read-sub")
            .audience(List.of("https://micor.top/api/mcp"))
            .issuedAt(Instant.now().minusSeconds(5)).expiresAt(Instant.now().plusSeconds(300))
            .claim("client_id",client).claim("scope",scope).build();
        when(decoder.decode("core-read-test")).thenReturn(jwt);
        when(links.resolveUserId("https://issuer.example.test","core-read-sub"))
            .thenReturn(OptionalLong.of(owner));
        when(users.findById(owner)).thenReturn(Optional.of(
            new UserAccount(owner,"synthetic","Synthetic","unused",false,true)));
        when(grants.grantedScopes(owner,client)).thenReturn(READ);
    }
    @BeforeEach void setup() { identity(2,CLIENT,"prp.tasks.read prp.wellness.read"); }

    MvcResult rpc(String name, Map<String,Object> arguments) throws Exception {
        var body=new LinkedHashMap<String,Object>();
        body.put("jsonrpc","2.0"); body.put("id",1);
        body.put("method",name==null?"tools/list":"tools/call");
        if(name!=null)body.put("params",Map.of("name",name,"arguments",arguments));
        var r=mvc.perform(post("/api/mcp").header("Authorization","Bearer core-read-test")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON,MediaType.TEXT_EVENT_STREAM)
            .content(json.writeValueAsString(body))).andReturn();
        if(r.getRequest().isAsyncStarted())r=mvc.perform(asyncDispatch(r)).andReturn();
        return r;
    }

    @Test void manifestAddsOnlyFiveOptInReadToolsWithScopes() throws Exception {
        var r=rpc(null,Map.of());
        assertThat(r.getResponse().getStatus()).isEqualTo(200);
        var toolsJson=json.readTree(r.getResponse().getContentAsString())
            .path("result").path("tools");
        assertThat(toolsJson.size()).isEqualTo(11);
        Set<String> names=new HashSet<>();
        for(var tool:toolsJson) {
            names.add(tool.path("name").asText());
            String scope=tool.path("_meta").path("securitySchemes").get(0)
                .path("scopes").get(0).asText();
            assertThat(READ).contains(scope);
            assertThat(tool.path("annotations").path("readOnlyHint").asBoolean()).isTrue();
        }
        assertThat(names).contains("prp_tasks_summary","prp_wellness_trends",
            "prp_wellness_goals","prp_wellness_frequent_foods","prp_wellness_dishes");
        assertThat(names).noneMatch(x -> x.startsWith("prp_prepare_"));
    }

    @Test void summaryUsesSharedBusinessService() throws Exception {
        when(tasks.summary()).thenReturn(new TaskSummary(3,1,0,1,1,2,Map.of("todo",3)));
        var response=rpc("prp_tasks_summary", Map.of());
        assertThat(response.getResponse().getStatus()).isEqualTo(200);
        assertThat(response.getResponse().getContentAsString()).contains("openCount","3");
        verify(tasks).summary();
        verifyNoInteractions(wellness);
    }

    @Test void trendReadHonorsDayLimitAndCallsServiceOnlyWithValidatedDays() throws Exception {
        when(wellness.trends(7)).thenReturn(List.of(
            new TrendPoint(LocalDate.of(2026,11,12),new BigDecimal("1500"),30,new BigDecimal("80.2"))));
        var response=rpc("prp_wellness_trends",Map.of("days",7));
        assertThat(response.getResponse().getStatus()).isEqualTo(200);
        assertThat(response.getResponse().getContentAsString()).contains("1500","80.2");
        verify(wellness).trends(7);
    }

    @Test void invalidTrendRangesNeverHitTheDatabaseService() throws Exception {
        for(int days:new int[]{0,91,-1}) {
            var result=rpc("prp_wellness_trends",Map.of("days",days));
            assertThat(result.getResponse().getContentAsString()).contains("\"isError\":true");
        }
        verifyNoInteractions(wellness,tasks);
    }

    @Test void goalAndDishReadAreBoundedAndOwnerServiceIsReused() throws Exception {
        var goals=IntStream.rangeClosed(1,25)
            .mapToObj(i->new Goal(i,LocalDate.of(2026,1,1),new BigDecimal("1800"),null,null))
            .toList();
        when(wellness.goals()).thenReturn(goals);
        var g=rpc("prp_wellness_goals",Map.of());
        assertThat(g.getResponse().getContentAsString()).contains("\"id\":20").doesNotContain("\"id\":25");
        when(wellness.dishTemplates("noodles")).thenReturn(List.of(new DishTemplate(
            5L,"Synthetic store","Noodles","one bowl",1,
            new BigDecimal("520"),"AI_ESTIMATE","synthetic")));
        var d=rpc("prp_wellness_dishes",Map.of("query","noodles"));
        assertThat(d.getResponse().getContentAsString()).contains("Noodles","520");
        verify(wellness).goals();
        verify(wellness).dishTemplates("noodles");
    }

    @Test void frequentFoodUsesOwnerScopedService() throws Exception {
        when(wellness.frequentFoods()).thenReturn(List.of(new Food(7L,"Synthetic egg","cooked",
            new BigDecimal("144"),new BigDecimal("13"),new BigDecimal("3"),new BigDecimal("9"),"reference",false)));
        var r=rpc("prp_wellness_frequent_foods",Map.of());
        assertThat(r.getResponse().getContentAsString()).contains("Synthetic egg");
        verify(wellness).frequentFoods();
    }

    @Test void missingScopeAndRevokedGrantCannotReadHealth() throws Exception {
        identity(2,CLIENT,"prp.tasks.read");
        var denied=rpc("prp_wellness_trends",Map.of("days",7));
        assertThat(denied.getResponse().getContentAsString()).contains("insufficient_scope","prp.wellness.read");
        verifyNoInteractions(wellness);
        identity(2,CLIENT,"prp.tasks.read prp.wellness.read");
        when(grants.grantedScopes(2,CLIENT)).thenReturn(Set.of());
        assertThat(rpc("prp_wellness_goals",Map.of()).getResponse().getStatus()).isEqualTo(401);
        verifyNoInteractions(wellness);
    }

    @Test void unallowlistedOwnerAndWrongClientCannotRead() throws Exception {
        identity(3,CLIENT,"prp.tasks.read prp.wellness.read");
        rpc("prp_wellness_goals",Map.of());
        identity(2,"other-client","prp.tasks.read prp.wellness.read");
        rpc("prp_wellness_goals",Map.of());
        verifyNoInteractions(wellness);
    }
}
