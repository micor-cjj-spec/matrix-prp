package com.matrix.prp.mcp;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.reviews.model.CreateReviewRequest;
import com.matrix.prp.reviews.service.ReviewService;
import com.matrix.prp.video.VideoDtos.FolderRequest;
import com.matrix.prp.video.VideoLibraryService;
import java.time.Instant;
import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.MockMvcPrint;
import org.springframework.boot.test.context.SpringBootTest;
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
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

/**
 * Disposable MySQL 8.4 + real PRP grant/link + actual MCP HTTP dispatch.
 * The JwtDecoder is mocked: token signatures/Keycloak PKCE are independently
 * verified in the existing OAuth E2E matrix. No live users or external services.
 */
@SpringBootTest
@AutoConfigureMockMvc(print = MockMvcPrint.NONE)
@ActiveProfiles("video-integration")
@TestPropertySource(properties={
    "matrix-prp.mcp.enabled=true",
    "matrix-prp.mcp.oauth.enabled=true",
    "matrix-prp.mcp.write-enabled=false",
    "matrix-prp.mcp.additional-read-tools-enabled=true",
    "matrix-prp.mcp.oauth.first-party-link.enabled=false",
    "matrix-prp.mcp.oauth.issuer=https://issuer.example.test",
    "matrix-prp.mcp.oauth.jwk-set-uri=https://issuer.example.test/jwks.json",
    "matrix-prp.mcp.oauth.resource=https://micor.top/api/mcp",
    "matrix-prp.mcp.oauth.advertised-scopes=prp.reviews.read,prp.video.read",
    "spring.ai.mcp.server.enabled=true",
    "matrix-prp.ai.spring-ai.enabled=false",
    "matrix-prp.ai.spring-ai.tools-enabled=false"
})
class McpReviewVideoOwnedMysqlOAuthIT {
    private static final String ISSUER="https://issuer.example.test";
    private static final String CLIENT="https://chatgpt.com/oauth/client.json";
    private static final String RESOURCE="https://micor.top/api/mcp";
    private static final List<String> READ_SCOPES=List.of("prp.reviews.read","prp.video.read");

    @Autowired UserStore users;
    @Autowired PasswordEncoder passwords;
    @Autowired McpIdentityLinkService links;
    @Autowired McpClientGrantService grants;
    @Autowired McpScopeGuard scopeGuard;
    @Autowired ReviewService reviews;
    @Autowired VideoLibraryService videos;
    @Autowired JdbcTemplate db;
    @Autowired ObjectMapper json;
    @Autowired MockMvc mvc;
    @MockitoBean(name="mcpJwtDecoder") JwtDecoder decoder;

    @AfterEach
    void clearTestPrincipalAndExpansion() {
        SecurityContextHolder.clearContext();
        scopeGuard.configureExpandedUsers("",CLIENT);
    }

    private UserAccount owner() {
        String username="ci_rv_oauth_"+UUID.randomUUID().toString().replace("-","").substring(0,14);
        return users.create(username,"Disposable OAuth owner",
            passwords.encode("disposable-pass"),false);
    }

    private void firstParty(UserAccount user) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(user.profile(),null,List.of()));
    }

    private String link(UserAccount user) {
        String subject="ci-rv-subject-"+UUID.randomUUID();
        firstParty(user);
        grants.authorize(CLIENT,READ_SCOPES,"disposable-pass");
        var ticket=links.issueTicket(CLIENT,"disposable-pass");
        links.complete(ticket.code(),ISSUER,subject,CLIENT);
        assertThat(links.resolveUserId(ISSUER,subject)).hasValue(user.id());
        return subject;
    }

    private void token(String value,String subject,String scope) {
        Jwt jwt=Jwt.withTokenValue(value).header("alg","RS256")
            .issuer(ISSUER).subject(subject).audience(List.of(RESOURCE))
            .issuedAt(Instant.now().minusSeconds(5))
            .expiresAt(Instant.now().plusSeconds(300))
            .claim("client_id",CLIENT).claim("scope",scope).build();
        when(decoder.decode(value)).thenReturn(jwt);
    }

    private MvcResult rpc(String token,String tool,Map<String,Object> args) throws Exception {
        var request=new LinkedHashMap<String,Object>();
        request.put("jsonrpc","2.0");
        request.put("id",1);
        request.put("method",tool==null?"tools/list":"tools/call");
        if(tool!=null)request.put("params",Map.of("name",tool,"arguments",args));
        MvcResult result=mvc.perform(post("/api/mcp")
            .header("Authorization","Bearer "+token)
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON,MediaType.TEXT_EVENT_STREAM)
            .content(json.writeValueAsString(request))).andReturn();
        if(result.getRequest().isAsyncStarted()) {
            result=mvc.perform(asyncDispatch(result)).andReturn();
        }
        return result;
    }

    @Test
    void twoRealOwnersReadOnlyOwnPreviewsThenRevocationBlocksSameBearer() throws Exception {
        UserAccount a=owner(),b=owner();
        String aSubject=link(a),bSubject=link(b);
        scopeGuard.configureExpandedUsers(a.id()+","+b.id(),CLIENT);

        firstParty(a);
        reviews.create(new CreateReviewRequest("weekly","learning",
            "OWNER_A_REVIEW","A preview","A_PRIVATE_HIGHLIGHTS",
            "A_PRIVATE_PROBLEMS","A_PRIVATE_ACTION",
            LocalDate.of(2026,11,1),LocalDate.of(2026,11,21)));
        var folderA=videos.createFolder(new FolderRequest(null,"OWNER_A_FOLDER"));
        db.update("INSERT INTO prp_video_assets (user_id,folder_id,title,storage_key,size_bytes) "+
                "VALUES (?,?,?,?,?)",a.id(),folderA.id(),"OWNER_A_VIDEO",UUID.randomUUID().toString(),16L);

        firstParty(b);
        reviews.create(new CreateReviewRequest("weekly","learning",
            "OWNER_B_REVIEW","B preview","B_PRIVATE_HIGHLIGHTS",
            "B_PRIVATE_PROBLEMS","B_PRIVATE_ACTION",
            LocalDate.of(2026,11,1),LocalDate.of(2026,11,21)));
        var folderB=videos.createFolder(new FolderRequest(null,"OWNER_B_FOLDER"));
        db.update("INSERT INTO prp_video_assets (user_id,folder_id,title,storage_key,size_bytes) "+
                "VALUES (?,?,?,?,?)",b.id(),folderB.id(),"OWNER_B_VIDEO",UUID.randomUUID().toString(),16L);

        // The mocked decoder supplies verified claims; other CI jobs validate real signatures.
        String bearerA="ci-rv-owner-a-"+UUID.randomUUID();
        String bearerB="ci-rv-owner-b-"+UUID.randomUUID();
        token(bearerA,aSubject,"prp.reviews.read prp.video.read");
        token(bearerB,bSubject,"prp.reviews.read prp.video.read");

        var list=rpc(bearerA,null,Map.of());
        assertThat(list.getResponse().getStatus()).isEqualTo(200);
        String catalog=list.getResponse().getContentAsString();
        assertThat(catalog).contains("prp_reviews_list","prp_video_folders","prp_video_progress");
        assertThat(catalog).doesNotContain("prp_prepare_task","prp_confirm_draft");

        for(var result:List.of(
            rpc(bearerA,"prp_reviews_list",Map.of("limit",20)),
            rpc(bearerA,"prp_video_folders",Map.of()),
            rpc(bearerA,"prp_video_progress",Map.of()))) {
            assertThat(result.getResponse().getStatus()).isEqualTo(200);
            String body=result.getResponse().getContentAsString();
            assertThat(body).doesNotContain("OWNER_B_","A_PRIVATE_","storageKey","playbackUrl");
        }
        assertThat(rpc(bearerA,"prp_reviews_list",Map.of()).getResponse().getContentAsString())
            .contains("OWNER_A_REVIEW").doesNotContain("OWNER_B_REVIEW");
        assertThat(rpc(bearerA,"prp_video_folders",Map.of()).getResponse().getContentAsString())
            .contains("OWNER_A_FOLDER").doesNotContain("OWNER_B_FOLDER");
        assertThat(rpc(bearerA,"prp_video_progress",Map.of()).getResponse().getContentAsString())
            .contains("OWNER_A_VIDEO").doesNotContain("OWNER_B_VIDEO");
        assertThat(rpc(bearerB,"prp_reviews_list",Map.of()).getResponse().getContentAsString())
            .contains("OWNER_B_REVIEW").doesNotContain("OWNER_A_REVIEW");
        assertThat(rpc(bearerB,"prp_video_progress",Map.of()).getResponse().getContentAsString())
            .contains("OWNER_B_VIDEO").doesNotContain("OWNER_A_VIDEO");

        String crossOwner=rpc(bearerB,"prp_video_progress",
            Map.of("folderId",folderA.id())).getResponse().getContentAsString();
        assertThat(crossOwner).contains("\"isError\":true").doesNotContain("OWNER_A_VIDEO");

        // A valid token does not survive real PRP owner-client grant revocation.
        firstParty(a);
        grants.revoke(CLIENT);
        assertThat(grants.grantedScopes(a.id(),CLIENT)).isEmpty();
        assertThat(rpc(bearerA,"prp_reviews_list",Map.of()).getResponse().getStatus())
            .isEqualTo(401);
        assertThat(rpc(bearerA,"prp_video_folders",Map.of()).getResponse().getStatus())
            .isEqualTo(401);
        assertThat(rpc(bearerB,"prp_video_folders",Map.of()).getResponse().getStatus())
            .isEqualTo(200);
    }
}
