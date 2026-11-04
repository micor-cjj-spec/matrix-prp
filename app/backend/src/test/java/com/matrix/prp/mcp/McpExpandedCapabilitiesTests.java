package com.matrix.prp.mcp;

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
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc(print=MockMvcPrint.NONE)
@ActiveProfiles("test")
@TestPropertySource(properties={"matrix-prp.mcp.enabled=true","matrix-prp.mcp.write-enabled=true",
 "matrix-prp.mcp.oauth.enabled=true","matrix-prp.mcp.expanded-user-ids=2",
 "matrix-prp.mcp.oauth.issuer=https://issuer.example.test",
 "matrix-prp.mcp.oauth.jwk-set-uri=https://issuer.example.test/jwks.json",
 "matrix-prp.mcp.oauth.resource=https://micor.top/api/mcp",
 "matrix-prp.mcp.oauth.advertised-scopes=prp.tasks.read,prp.finance.read,prp.wellness.read,prp.write.create,prp.write.update,prp.write.delete,prp.write.status,prp.write.confirm",
 "spring.ai.mcp.server.enabled=true"})
class McpExpandedCapabilitiesTests {
 static final String CLIENT="https://chatgpt.com/oauth/client.json";
 static final String SCOPES="prp.tasks.read prp.finance.read prp.wellness.read prp.write.create prp.write.update prp.write.delete prp.write.status prp.write.confirm";
 @Autowired MockMvc mvc;
 @MockitoBean UserStore users;
 @MockitoBean JdbcTemplate jdbc;
 @MockitoBean McpClientGrantService grants;
 @MockitoBean McpIdentityLinkService links;
 @MockitoBean WellnessService wellness;
 @MockitoBean(name="mcpJwtDecoder") JwtDecoder decoder;
 void identity(long owner,String client,String scopes) {
  var jwt=Jwt.withTokenValue("expanded-test").header("alg","RS256").issuer("https://issuer.example.test")
   .subject("expanded-subject").audience(List.of("https://micor.top/api/mcp"))
   .issuedAt(Instant.now().minusSeconds(5)).expiresAt(Instant.now().plusSeconds(300))
   .claim("client_id",client).claim("scope",scopes).build();
  when(decoder.decode("expanded-test")).thenReturn(jwt);
  when(links.resolveUserId("https://issuer.example.test","expanded-subject")).thenReturn(OptionalLong.of(owner));
  when(users.findById(owner)).thenReturn(Optional.of(new UserAccount(owner,"synthetic","Synthetic","unused-hash",false,true)));
  when(grants.grantedScopes(owner,client)).thenReturn(Set.of(SCOPES.split(" ")));
 }
 @BeforeEach void setup(){identity(2,CLIENT,SCOPES);}
 MvcResult request(String body) throws Exception {
  var result=mvc.perform(post("/api/mcp").header("Authorization","Bearer expanded-test")
   .contentType(MediaType.APPLICATION_JSON).accept(MediaType.APPLICATION_JSON,MediaType.TEXT_EVENT_STREAM).content(body)).andReturn();
  if(result.getRequest().isAsyncStarted())result=mvc.perform(asyncDispatch(result)).andReturn();
  return result;
 }
 static String prepare(){return "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"prp_prepare_task\",\"arguments\":{\"moduleCode\":\"work\",\"title\":\"Synthetic expanded draft\"}}}";}
 @Test void advertisesExactlyEightBusinessScopes() throws Exception {
  mvc.perform(get("/.well-known/oauth-protected-resource/api/mcp")).andExpect(status().isOk())
   .andExpect(jsonPath("$.scopes_supported.length()").value(8));
 }
 @Test void allTwelveExistingToolsAreDiscoverable() throws Exception {
  var r=request("{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\"}");
  assertThat(r.getResponse().getStatus()).isEqualTo(200);
  assertThat(r.getResponse().getContentAsString()).contains("prp_prepare_task","prp_prepare_task_update","prp_prepare_task_delete","prp_prepare_finance","prp_prepare_record","prp_prepare_meal","prp_confirm_draft","prp_wellness_daily");
  verifyNoInteractions(jdbc);
 }
 @Test void whitespaceScopesPassRealSecurityChainAndDraftRemainsOwnerBound() throws Exception {
  when(jdbc.queryForObject(anyString(),eq(Integer.class),eq(2L))).thenReturn(0);
  var r=request(prepare());assertThat(r.getResponse().getStatus()).isEqualTo(200);
  assertThat(r.getResponse().getContentAsString()).contains("draftId","Synthetic expanded draft").doesNotContain("\"isError\":true");
  verify(jdbc).update(startsWith("INSERT INTO prp_mcp_write_drafts"),any(),eq(2L),eq("TASK"),any(),any());
 }
 @Test void realMcpTransportDecodesStructuredMealItemsAndOnlyPreparesDraft() throws Exception {
  when(jdbc.queryForObject(anyString(),eq(Integer.class),eq(2L))).thenReturn(0);
  String requestBody = """
    {"jsonrpc":"2.0","id":43,"method":"tools/call","params":{"name":"prp_prepare_meal",
    "arguments":{"mealDate":"2026-11-04","mealType":"LUNCH",
    "items":[{"foodId":null,"name":"synthetic chicken","grams":180,"calories":360.00},
             {"foodId":null,"name":"synthetic wontons","grams":200,"calories":260.00}],
    "note":"owner-reviewed estimates"}}}
    """;
  var response=request(requestBody);
  assertThat(response.getResponse().getStatus()).isEqualTo(200);
  var mapper=new com.fasterxml.jackson.databind.ObjectMapper();
  var rpc=mapper.readTree(response.getResponse().getContentAsString());
  assertThat(rpc.path("result").path("isError").asBoolean()).isFalse();
  var proposal=mapper.readTree(rpc.path("result").path("content").get(0).path("text").asText());
  assertThat(proposal.path("draftId").asText()).isNotBlank();
  assertThat(proposal.path("kind").asText()).isEqualTo("MEAL");
  assertThat(proposal.path("values").path("items").get(0).path("calories").decimalValue())
      .isEqualByComparingTo("360.00");
  verify(wellness).validateMcpMealInput(eq(java.time.LocalDate.of(2026,11,4)),
      eq("LUNCH"), eq("owner-reviewed estimates"), anyList());
  verify(jdbc).update(startsWith("INSERT INTO prp_mcp_write_drafts"),
      any(),eq(2L),eq("MEAL"),any(),any());
  verify(wellness,never()).addAiMeal(any(),any(),any(),any(),any());
 }
 @Test void realMcpTransportRejectsMealMissingCalorieEstimate() throws Exception {
  String requestBody = """
    {"jsonrpc":"2.0","id":44,"method":"tools/call","params":{"name":"prp_prepare_meal",
    "arguments":{"mealDate":"2026-11-04","mealType":"LUNCH",
    "items":[{"foodId":null,"name":"synthetic chicken","grams":180}]}}}
    """;
  var response=request(requestBody);
  assertThat(response.getResponse().getStatus()).isEqualTo(200);
  assertThat(response.getResponse().getContentAsString()).contains("isError");
  verify(jdbc,never()).update(startsWith("INSERT INTO prp_mcp_write_drafts"),
      any(),any(),any(),any(),any());
  verify(wellness,never()).addAiMeal(any(),any(),any(),any(),any());
 }
 @Test void anotherAccountIsDeniedEvenWithAllSignedScopesAndGrant() throws Exception {
  identity(1,CLIENT,SCOPES);request(prepare());verifyNoInteractions(jdbc);
 }
 @Test void anotherClientIsDeniedEvenForAllowedOwner() throws Exception {
  identity(2,"different-client",SCOPES);request(prepare());verifyNoInteractions(jdbc);
 }
 @Test void oldReadTokenDoesNotGainWritePermission() throws Exception {
  identity(2,CLIENT,"prp.tasks.read");request(prepare());verifyNoInteractions(jdbc);
 }
 @Test void grantRevocationImmediatelyRejectsUnexpiredToken() throws Exception {
  when(grants.grantedScopes(2,CLIENT)).thenReturn(Set.of());assertThat(request(prepare()).getResponse().getStatus()).isEqualTo(401);verifyNoInteractions(jdbc);
 }
 @Test void tokenClaimsCannotChooseAnotherOwner() throws Exception {
  identity(1,CLIENT,SCOPES);request(prepare());verifyNoInteractions(jdbc);
 }
 @Test void unapprovedOrUnknownDraftNeverWritesBusinessData() throws Exception {
  request("{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"prp_confirm_draft\",\"arguments\":{\"draftId\":\"41abc027-d67e-4bdf-8985-e3ec97d23204\"}}}");
  verify(jdbc,never()).update(startsWith("UPDATE prp_mcp_write_drafts SET status='CONSUMED'"),any(),any(),any());
 }
}
