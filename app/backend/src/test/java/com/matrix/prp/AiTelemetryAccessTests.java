package com.matrix.prp;

import static org.assertj.core.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.ai.AiInvocationAudit;
import com.matrix.prp.auth.repository.UserStore;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc(print=org.springframework.boot.test.autoconfigure.web.servlet.MockMvcPrint.NONE)
@ActiveProfiles("test")
class AiTelemetryAccessTests {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired UserStore users;
    @Autowired AiInvocationAudit audit;

    private String login(String name,String password) throws Exception {
        String body=json.writeValueAsString(Map.of("username",name,"password",password));
        return json.readTree(mvc.perform(post("/api/auth/login")
            .contentType(MediaType.APPLICATION_JSON).content(body))
            .andExpect(status().isOk()).andReturn().getResponse().getContentAsString())
            .path("data").path("token").asText();
    }

    @Test void onlyOwnMetricsVisibleAndQueryValidated() throws Exception {
        String admin=login("admin","matrix-prp");
        long adminId=users.findByUsername("admin").orElseThrow().id();
        audit.record(new AiInvocationAudit.Entry(adminId,"deepseek","deepseek-chat","SERVER",
            "SUCCESS",null,120L,10L,6L,2L,LocalDateTime.now(Clock.systemUTC())));
        mvc.perform(get("/api/ai/telemetry")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/ai/telemetry").param("days","2")
            .header(HttpHeaders.AUTHORIZATION,"Bearer "+admin)).andExpect(status().isBadRequest());
        mvc.perform(get("/api/ai/telemetry").param("limit","1000")
            .header(HttpHeaders.AUTHORIZATION,"Bearer "+admin)).andExpect(status().isBadRequest());
        var result=mvc.perform(get("/api/ai/telemetry").param("days","7")
            .header(HttpHeaders.AUTHORIZATION,"Bearer "+admin))
            .andExpect(status().isOk())
            .andExpect(header().string(HttpHeaders.CACHE_CONTROL,"no-store"))
            .andExpect(jsonPath("$.data.summary.totalRequests").value(org.hamcrest.Matchers.greaterThanOrEqualTo(1)))
            .andExpect(jsonPath("$.data.costStatus").value("UNAVAILABLE_NO_VERIFIED_MODEL_PRICING"))
            .andReturn().getResponse().getContentAsString();
        assertThat(result).doesNotContain("matrix-prp","apiKey","prompt","PRIVATE");
        assertThat(result).contains("deepseek-chat");

        String invitation=json.readTree(mvc.perform(post("/api/auth/invitations")
            .header(HttpHeaders.AUTHORIZATION,"Bearer "+admin))
            .andExpect(status().isOk()).andReturn().getResponse().getContentAsString())
            .path("data").path("code").asText();
        mvc.perform(post("/api/auth/register").contentType(MediaType.APPLICATION_JSON)
            .content(json.writeValueAsString(Map.of(
                "username","telemetry_peer_20261020","password","test-peer-password-2026",
                "displayName","Telemetry Peer","invitationCode",invitation))))
            .andExpect(status().isOk());
        String peer=login("telemetry_peer_20261020","test-peer-password-2026");
        mvc.perform(get("/api/ai/telemetry").header(HttpHeaders.AUTHORIZATION,"Bearer "+peer))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.summary.totalRequests").value(0))
            .andExpect(jsonPath("$.data.recent.length()").value(0));
    }
}
