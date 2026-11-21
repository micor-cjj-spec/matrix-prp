package com.matrix.prp.mcp;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.reviews.model.ReviewFilter;
import com.matrix.prp.reviews.model.ReviewItem;
import com.matrix.prp.reviews.service.ReviewService;
import com.matrix.prp.video.VideoDtos.Folder;
import com.matrix.prp.video.VideoDtos.Video;
import com.matrix.prp.video.VideoLibraryService;
import com.matrix.prp.records.service.RecordService;
import com.matrix.prp.tasks.service.TaskService;
import com.matrix.prp.wellness.WellnessService;
import java.time.*;
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
    "matrix-prp.mcp.oauth.advertised-scopes=prp.reviews.read,prp.video.read",
    "spring.ai.mcp.server.enabled=true"
})
class McpReviewVideoOAuthTests {
    private static final String CLIENT="https://chatgpt.com/oauth/client.json";
    private static final String TOKEN="synthetic-review-video-token";
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @MockitoBean UserStore users;
    @MockitoBean JdbcTemplate jdbc;
    @MockitoBean McpClientGrantService grants;
    @MockitoBean McpIdentityLinkService links;
    @MockitoBean ReviewService reviews;
    @MockitoBean VideoLibraryService videos;
    @MockitoBean TaskService tasks;
    @MockitoBean RecordService records;
    @MockitoBean WellnessService wellness;
    @MockitoBean(name="mcpJwtDecoder") JwtDecoder decoder;

    private void identity(long owner,String client,String tokenScopes,Set<String> consent) {
        var jwt=Jwt.withTokenValue(TOKEN).header("alg","RS256")
            .issuer("https://issuer.example.test").subject("synthetic-rv-user")
            .audience(List.of("https://micor.top/api/mcp"))
            .issuedAt(Instant.now().minusSeconds(5)).expiresAt(Instant.now().plusSeconds(300))
            .claim("client_id",client).claim("scope",tokenScopes).build();
        when(decoder.decode(TOKEN)).thenReturn(jwt);
        when(links.resolveUserId("https://issuer.example.test","synthetic-rv-user"))
            .thenReturn(OptionalLong.of(owner));
        when(users.findById(owner)).thenReturn(Optional.of(
            new UserAccount(owner,"synthetic","Synthetic","unused-hash",false,true)));
        when(grants.grantedScopes(owner,client)).thenReturn(consent);
    }
    @BeforeEach void setup() {
        identity(2,CLIENT,"prp.reviews.read prp.video.read",
            Set.of("prp.reviews.read","prp.video.read"));
    }
    private MvcResult rpc(String name,Map<String,Object> args) throws Exception {
        var body=new LinkedHashMap<String,Object>();
        body.put("jsonrpc","2.0");body.put("id",1);
        body.put("method",name==null?"tools/list":"tools/call");
        if(name!=null)body.put("params",Map.of("name",name,"arguments",args));
        var result=mvc.perform(post("/api/mcp").header("Authorization","Bearer "+TOKEN)
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON,MediaType.TEXT_EVENT_STREAM)
            .content(json.writeValueAsString(body))).andReturn();
        if(result.getRequest().isAsyncStarted())result=mvc.perform(asyncDispatch(result)).andReturn();
        return result;
    }

    @Test void listShowsOnlyThreeOptInReadToolsWithSeparateScopes() throws Exception {
        var result=rpc(null,Map.of());
        assertThat(result.getResponse().getStatus()).isEqualTo(200);
        var tools=json.readTree(result.getResponse().getContentAsString())
            .path("result").path("tools");
        assertThat(tools.size()).isEqualTo(3);
        var names=new HashSet<String>();
        for(var item:tools) {
            var name=item.path("name").asText();
            names.add(name);
            assertThat(item.path("annotations").path("readOnlyHint").asBoolean()).isTrue();
            // The client must never select an account or supply media credentials.
            var properties=item.path("inputSchema").path("properties");
            assertThat(properties.has("userId")).isFalse();
            assertThat(properties.has("ownerId")).isFalse();
            assertThat(properties.has("ticket")).isFalse();
            assertThat(properties.has("playbackUrl")).isFalse();
            var scope=item.path("_meta").path("securitySchemes").get(0)
                .path("scopes").get(0).asText();
            assertThat(scope).isEqualTo("prp_reviews_list".equals(name)
                ?"prp.reviews.read":"prp.video.read");
        }
        assertThat(names).containsExactlyInAnyOrder(
            "prp_reviews_list","prp_video_folders","prp_video_progress");
    }

    @Test void reviewPreviewsExcludePrivateContentAndCheckScope() throws Exception {
        var period=LocalDate.of(2026,11,1);
        when(reviews.listLimited(any(ReviewFilter.class),eq(3))).thenReturn(List.of(
            new ReviewItem(7,"weekly","learning","Sample review","Public preview",
                "PRIVATE_HIGHLIGHTS","PRIVATE_PROBLEMS","PRIVATE_ACTION",
                period,period,OffsetDateTime.parse("2026-11-02T00:00:00Z"))));
        var r=rpc("prp_reviews_list",Map.of("reviewType","weekly","limit",3));
        var content=r.getResponse().getContentAsString();
        assertThat(r.getResponse().getStatus()).isEqualTo(200);
        assertThat(content).contains("Sample review","Public preview")
            .doesNotContain("PRIVATE_HIGHLIGHTS","PRIVATE_PROBLEMS","PRIVATE_ACTION");
        verify(reviews).listLimited(any(ReviewFilter.class),eq(3));
        verifyNoInteractions(videos);
    }

    @Test void videoFolderAndProgressNeverIssueMediaTickets() throws Exception {
        when(videos.foldersLimited(2)).thenReturn(List.of(new Folder(9,null,"Videos",0)));
        when(videos.videosLimited(9L,2)).thenReturn(List.of(
            new Video(10,9L,"Lesson 1",1234,LocalDateTime.of(2026,11,1,8,0),40,200)));
        var folder=rpc("prp_video_folders",Map.of("limit",2)).getResponse().getContentAsString();
        var progress=rpc("prp_video_progress",Map.of("folderId",9,"limit",2))
            .getResponse().getContentAsString();
        assertThat(folder).contains("Videos");
        assertThat(progress).contains("Lesson 1","positionSeconds","durationSeconds")
            .doesNotContain("ticket","storageKey","sizeBytes","playbackUrl");
        verify(videos).foldersLimited(2);
        verify(videos).videosLimited(9L,2);
        verifyNoMoreInteractions(videos);
        verifyNoInteractions(reviews);
    }

    @Test void invalidInputDoesNotReachReadServices() throws Exception {
        for(var t:List.of(
            Map.entry("prp_reviews_list",Map.<String,Object>of("limit",21)),
            Map.entry("prp_reviews_list",Map.<String,Object>of("periodStart","not-a-date")),
            Map.entry("prp_video_folders",Map.<String,Object>of("limit",51)),
            Map.entry("prp_video_progress",Map.<String,Object>of("folderId",-1)))) {
            assertThat(rpc(t.getKey(),t.getValue()).getResponse().getContentAsString())
                .contains("\"isError\":true");
        }
        verifyNoInteractions(reviews,videos);
    }

    @Test void unexpectedOAuthClientCannotReadReviewOrVideo() throws Exception {
        identity(2,"https://client.example.test/oauth/client.json",
            "prp.reviews.read prp.video.read",Set.of("prp.reviews.read","prp.video.read"));
        rpc("prp_reviews_list",Map.of());
        rpc("prp_video_progress",Map.of());
        verifyNoInteractions(reviews,videos);
    }

    @Test void unlinkedOAuthIdentityCannotReadEvenIfTokenHasScopes() throws Exception {
        when(links.resolveUserId("https://issuer.example.test","synthetic-rv-user"))
            .thenReturn(OptionalLong.empty());
        assertThat(rpc("prp_reviews_list",Map.of()).getResponse().getStatus()).isEqualTo(401);
        verifyNoInteractions(reviews,videos);
    }

    @Test void missingScopeRevokedConsentAndUnapprovedOwnerAllFailClosed() throws Exception {
        identity(2,CLIENT,"prp.video.read",Set.of("prp.reviews.read","prp.video.read"));
        assertThat(rpc("prp_reviews_list",Map.of()).getResponse().getContentAsString())
            .contains("insufficient_scope","prp.reviews.read");
        identity(2,CLIENT,"prp.reviews.read prp.video.read",Set.of());
        assertThat(rpc("prp_video_folders",Map.of()).getResponse().getStatus()).isEqualTo(401);
        identity(3,CLIENT,"prp.reviews.read prp.video.read",
            Set.of("prp.reviews.read","prp.video.read"));
        rpc("prp_reviews_list",Map.of());
        verifyNoInteractions(reviews,videos);
    }
}
