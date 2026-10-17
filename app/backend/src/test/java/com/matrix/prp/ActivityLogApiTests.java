package com.matrix.prp;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import static org.assertj.core.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
@SpringBootTest
@AutoConfigureMockMvc(print=org.springframework.boot.test.autoconfigure.web.servlet.MockMvcPrint.NONE)
@ActiveProfiles("test")
class ActivityLogApiTests {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    private String login(String user,String pass) throws Exception {
        String text=mvc.perform(post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
            .content(json.writeValueAsString(Map.of("username",user,"password",pass))))
            .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        return json.readTree(text).path("data").path("token").asText();
    }
    @Test void httpAuditIsOwnerScopedAndMeasuresElapsedTime() throws Exception {
        String admin=login("admin","matrix-prp");
        String invite=json.readTree(mvc.perform(post("/api/auth/invitations")
            .header(HttpHeaders.AUTHORIZATION,"Bearer "+admin)).andExpect(status().isOk())
            .andReturn().getResponse().getContentAsString()).path("data").path("code").asText();
        String username="audit_"+System.nanoTime();
        mvc.perform(post("/api/auth/register").contentType(MediaType.APPLICATION_JSON)
            .content(json.writeValueAsString(Map.of("username",username,
                "password","test-friend-password","displayName","Log Friend","invitationCode",invite))))
            .andExpect(status().isOk());
        String friend=login(username,"test-friend-password");
        mvc.perform(get("/api/ai/usage").header(HttpHeaders.AUTHORIZATION,"Bearer "+admin)).andExpect(status().isOk());
        mvc.perform(get("/api/ai/usage").header(HttpHeaders.AUTHORIZATION,"Bearer "+friend)).andExpect(status().isOk());
        String body=mvc.perform(get("/api/activity/mine").header(HttpHeaders.AUTHORIZATION,"Bearer "+friend))
            .andExpect(status().isOk()).andExpect(header().string(HttpHeaders.CACHE_CONTROL,"no-store"))
            .andReturn().getResponse().getContentAsString();
        var entries=json.readTree(body).path("data");
        assertThat(entries.isArray()).isTrue();
        assertThat(entries.toString()).contains("GET /api/ai/usage").doesNotContain("Authorization");
        assertThat(entries.get(0).path("elapsedMs").asLong()).isGreaterThanOrEqualTo(0);
        mvc.perform(get("/api/activity/mine").param("days","2")
            .header(HttpHeaders.AUTHORIZATION,"Bearer "+friend)).andExpect(status().isBadRequest());
        mvc.perform(get("/api/activity/mine").param("limit","100")
            .header(HttpHeaders.AUTHORIZATION,"Bearer "+friend)).andExpect(status().isBadRequest());
        mvc.perform(get("/api/activity/mine")).andExpect(status().isUnauthorized());
    }
}
