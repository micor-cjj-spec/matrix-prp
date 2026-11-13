package com.matrix.prp.mcp;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.jwt.Jwt;
import static org.mockito.Mockito.*;
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
class McpLegacyFallbackTests extends McpOAuthSecurityTests {
 private static final String D="{\"jsonrpc\":\"2.0\",\"id\":\"fallback\",\"method\":\"server/discover\",\"params\":{\"_meta\":{\"io.modelcontextprotocol/protocolVersion\":\"2026-07-28\"}}}";
 @BeforeEach void setupIdentity(){
 var j=Jwt.withTokenValue("fallback-test").header("alg","RS256").issuer("https://issuer.example.test").subject("fallback-subject").audience(List.of("https://micor.top/api/mcp")).issuedAt(Instant.now().minusSeconds(5)).expiresAt(Instant.now().plusSeconds(300)).claim("client_id","fallback-client").claim("scope","prp.tasks.read").build();
 when(oauthDecoder.decode("fallback-test")).thenReturn(j);
 when(identityLinks.resolveUserId("https://issuer.example.test","fallback-subject")).thenReturn(OptionalLong.of(1));
 when(clientGrants.grantedScopes(1,"fallback-client")).thenReturn(Set.of("prp.tasks.read"));
 }
 private org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder req(String b){return post("/api/mcp").header("Authorization","Bearer fallback-test").contentType(MediaType.APPLICATION_JSON).accept(MediaType.APPLICATION_JSON,MediaType.TEXT_EVENT_STREAM).content(b);}
 @Test void modernDiscoveryIsLegacyFallbackNotInconsistentSuccess() throws Exception {
 mvc.perform(req(D).header("MCP-Protocol-Version","2026-07-28")).andExpect(status().isBadRequest()).andExpect(jsonPath("$.id").value("fallback")).andExpect(jsonPath("$.error.code").value(-32601)).andExpect(jsonPath("$.result").doesNotExist()).andExpect(jsonPath("$.error.data.supported").doesNotExist());verifyNoInteractions(jdbc);
 }
 @Test void modernDirectRpcDoesNotFalselyIdentifyModernServer() throws Exception {mvc.perform(req(D.replace("server/discover","tools/list"))).andExpect(status().isBadRequest()).andExpect(jsonPath("$.error.code").value(-32601));}
 @Test void fallbackThenActualLegacyInitializeAndReadTools() throws Exception {
 mvc.perform(req(D)).andExpect(status().isBadRequest());
 var init=mvc.perform(req("{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2025-11-25\",\"capabilities\":{},\"clientInfo\":{\"name\":\"fallback-test\",\"version\":\"1\"}}}")).andReturn();
 if(init.getRequest().isAsyncStarted())init=mvc.perform(asyncDispatch(init)).andReturn();
 assertThat(init.getResponse().getStatus()).isEqualTo(200);assertThat(init.getResponse().getContentAsString()).contains("2025-11-25");
 var list=mvc.perform(req("{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/list\",\"params\":{}}" )).andReturn();if(list.getRequest().isAsyncStarted())list=mvc.perform(asyncDispatch(list)).andReturn();assertThat(list.getResponse().getStatus()).isEqualTo(200);assertThat(list.getResponse().getContentAsString()).contains("prp_tasks_list","prp_task_get").doesNotContain("prp_prepare_task","prp_confirm_draft");verifyNoInteractions(jdbc);
 }
 @Test void anonymousStill401() throws Exception {mvc.perform(post("/api/mcp").contentType(MediaType.APPLICATION_JSON).content(D)).andExpect(status().isUnauthorized()).andExpect(header().exists("WWW-Authenticate"));}
 @Test void revokedStill401() throws Exception {when(clientGrants.grantedScopes(1,"fallback-client")).thenReturn(Set.of());mvc.perform(req(D)).andExpect(status().isUnauthorized());}
 @Test void unlinkedStill401() throws Exception {when(identityLinks.resolveUserId("https://issuer.example.test","fallback-subject")).thenReturn(OptionalLong.empty());mvc.perform(req(D)).andExpect(status().isUnauthorized());}
 @Test void mismatchedVersionStill400() throws Exception {mvc.perform(req(D).header("MCP-Protocol-Version","2025-11-25")).andExpect(status().isBadRequest()).andExpect(jsonPath("$.error.code").value(-32020));}
 @Test void malformedStillRejected() throws Exception {mvc.perform(req("{broken")).andExpect(status().isBadRequest());mvc.perform(req(D+"{}")).andExpect(status().isBadRequest());}
 @Test void oversizedStillRejected() throws Exception {mvc.perform(req("x".repeat(32769))).andExpect(status().isPayloadTooLarge());}
 @Test void duplicateStillRejected() throws Exception {mvc.perform(req(D.replace("\"method\":","\"method\":\"tools/list\",\"method\":"))).andExpect(status().isBadRequest());}
}
