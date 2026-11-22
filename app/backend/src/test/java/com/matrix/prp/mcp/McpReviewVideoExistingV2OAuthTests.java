package com.matrix.prp.mcp;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.finance.service.FinanceService;
import com.matrix.prp.practice.PracticeService;
import com.matrix.prp.records.service.RecordService;
import com.matrix.prp.reviews.service.ReviewService;
import com.matrix.prp.tasks.model.TaskFilter;
import com.matrix.prp.tasks.service.TaskService;
import com.matrix.prp.video.VideoLibraryService;
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
 * Mocked-issuer OAuth protocol regression for the live V2 scope *shape*:
 * eight pre-existing scopes plus two optional review/video reads.
 * No live MySQL, Keycloak, deployment, credentials or user data.
 */
@SpringBootTest
@AutoConfigureMockMvc(print=MockMvcPrint.NONE)
@ActiveProfiles("test")
@TestPropertySource(properties={
    "matrix-prp.mcp.enabled=true",
    "matrix-prp.mcp.write-enabled=true",
    "matrix-prp.mcp.oauth.enabled=true",
    "matrix-prp.mcp.additional-read-tools-enabled=false",
    "matrix-prp.mcp.review-video-read-tools-enabled=true",
    "matrix-prp.mcp.expanded-user-ids=2",
    "matrix-prp.mcp.oauth.issuer=https://issuer.example.test",
    "matrix-prp.mcp.oauth.jwk-set-uri=https://issuer.example.test/jwks.json",
    "matrix-prp.mcp.oauth.resource=https://micor.top/api/mcp",
    "matrix-prp.mcp.oauth.advertised-scopes=prp.tasks.read,prp.finance.read,prp.wellness.read,prp.write.create,prp.write.update,prp.write.delete,prp.write.status,prp.write.confirm,prp.reviews.read,prp.video.read",
    "spring.ai.mcp.server.enabled=true"
})
class McpReviewVideoExistingV2OAuthTests {
    private static final String CLIENT="https://chatgpt.com/oauth/client.json";
    private static final String ISSUER="https://issuer.example.test";
    private static final String RESOURCE="https://micor.top/api/mcp";
    private static final String TOKEN="synthetic-v2-ten-scope-test";
    private static final Set<String> EXISTING=Set.of(
        "prp.tasks.read","prp.finance.read","prp.wellness.read",
        "prp.write.create","prp.write.update","prp.write.delete",
        "prp.write.status","prp.write.confirm");
    private static final Set<String> NEW_READ=Set.of("prp.reviews.read","prp.video.read");
    private static final Set<String> ALL;
    static {
        var scopes=new HashSet<>(EXISTING);
        scopes.addAll(NEW_READ);
        ALL=Set.copyOf(scopes);
    }
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
    @MockitoBean ReviewService reviews;
    @MockitoBean VideoLibraryService videos;
    @MockitoBean(name="mcpJwtDecoder") JwtDecoder decoder;

    @BeforeEach void authenticate() {
        var jwt=Jwt.withTokenValue(TOKEN).header("alg","RS256")
            .issuer(ISSUER).subject("synthetic-v2-owner").audience(List.of(RESOURCE))
            .issuedAt(Instant.now().minusSeconds(5))
            .expiresAt(Instant.now().plusSeconds(300))
            .claim("client_id",CLIENT).claim("scope",String.join(" ",ALL)).build();
        when(decoder.decode(TOKEN)).thenReturn(jwt);
        when(links.resolveUserId(ISSUER,"synthetic-v2-owner"))
            .thenReturn(OptionalLong.of(2));
        when(users.findById(2L)).thenReturn(Optional.of(
            new UserAccount(2,"synthetic","Synthetic","unused-hash",false,true)));
        when(grants.grantedScopes(2,CLIENT)).thenReturn(ALL);
    }

    private MvcResult rpc(String tool) throws Exception {
        var payload=new LinkedHashMap<String,Object>();
        payload.put("jsonrpc","2.0");
        payload.put("id",1);
        payload.put("method",tool==null?"tools/list":"tools/call");
        if(tool!=null)payload.put("params",Map.of("name",tool,"arguments",Map.of()));
        var result=mvc.perform(post("/api/mcp")
            .header("Authorization","Bearer "+TOKEN)
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON,MediaType.TEXT_EVENT_STREAM)
            .content(json.writeValueAsString(payload))).andReturn();
        if(result.getRequest().isAsyncStarted())
            result=mvc.perform(asyncDispatch(result)).andReturn();
        return result;
    }

    @Test void existingEightScopeToolsPreservedAndExactlyThreeNewReadsAppear() throws Exception {
        var result=rpc(null);
        assertThat(result.getResponse().getStatus()).isEqualTo(200);
        var manifest=json.readTree(result.getResponse().getContentAsString())
            .path("result").path("tools");
        Set<String> baseline=McpToolConfiguration.exposedNames(
            "prp.tasks.read,prp.finance.read,prp.wellness.read,prp.write.create,"
                +"prp.write.update,prp.write.delete,prp.write.status,prp.write.confirm",
            true,false,false);
        var expected=new HashSet<>(baseline);
        expected.addAll(Set.of("prp_reviews_list","prp_video_folders","prp_video_progress"));
        var found=new HashSet<String>();
        for(var tool:manifest) {
            String name=tool.path("name").asText();
            assertThat(found.add(name)).isTrue();
            String required=tool.path("_meta").path("securitySchemes")
                .get(0).path("scopes").get(0).asText();
            assertThat(ALL).contains(required);
            if(Set.of("prp_reviews_list","prp_video_folders","prp_video_progress").contains(name)) {
                assertThat(tool.path("annotations").path("readOnlyHint").asBoolean()).isTrue();
                assertThat(NEW_READ).contains(required);
            }
        }
        assertThat(found).containsExactlyInAnyOrderElementsOf(expected)
            .doesNotContain("prp_tasks_search","prp_tasks_summary","prp_wellness_trends",
                "prp_wellness_goals","prp_wellness_frequent_foods","prp_wellness_dishes");
        assertThat(found).contains("prp_prepare_task","prp_confirm_draft");
    }

    @Test void reducingOwnerGrantToExistingEightRevokesOnlyNewReads() throws Exception {
        when(grants.grantedScopes(2,CLIENT)).thenReturn(EXISTING);
        var declined=rpc("prp_video_folders");
        assertThat(declined.getResponse().getContentAsString())
            .contains("\"isError\":true");
        verifyNoInteractions(videos,reviews);

        when(tasks.listLimited(any(TaskFilter.class),eq(20))).thenReturn(List.of());
        var oldTaskRead=rpc("prp_tasks_list");
        assertThat(oldTaskRead.getResponse().getStatus()).isEqualTo(200);
        assertThat(oldTaskRead.getResponse().getContentAsString())
            .contains("\"isError\":false");
        verify(tasks).listLimited(any(TaskFilter.class),eq(20));
    }
}
