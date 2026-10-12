package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.ai.AgentTaskStore;
import com.matrix.prp.ai.OpenClawGatewayClient;
import com.matrix.prp.auth.repository.UserStore;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class AgentTaskAccessTests {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired AgentTaskStore store;
    @Autowired UserStore users;
    @MockitoBean OpenClawGatewayClient gateway;

    @BeforeEach void mockGateway() throws Exception {
        when(gateway.configured()).thenReturn(true);
        when(gateway.generate(any(AgentTaskStore.AgentTask.class))).thenReturn("Written plan only");
    }
    private String login(String name, String pass) throws Exception {
        String response = mvc.perform(post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
            .content(json.writeValueAsString(Map.of("username",name,"password",pass))))
            .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        return "Bearer " + json.readTree(response).path("data").path("token").asText();
    }
    private String create(String authorization, String type, String prompt) throws Exception {
        return json.readTree(mvc.perform(post("/api/ai/agent/tasks")
            .header(HttpHeaders.AUTHORIZATION, authorization)
            .contentType(MediaType.APPLICATION_JSON)
            .content(json.writeValueAsString(Map.of("taskType",type,"prompt",prompt))))
            .andExpect(status().isCreated())
            .andExpect(header().string(HttpHeaders.CACHE_CONTROL, "no-store"))
            .andReturn().getResponse().getContentAsString()).path("data").path("id").asText();
    }

    @Test void requiresApprovalAndExecutesOnce() throws Exception {
        String admin = login("admin", "matrix-prp");
        String id = create(admin,"PLAN","Plan a safe learning schedule");
        mvc.perform(get("/api/ai/agent/tasks/{id}", id).header(HttpHeaders.AUTHORIZATION,admin))
            .andExpect(jsonPath("$.data.status").value("PENDING_APPROVAL"));
        mvc.perform(post("/api/ai/agent/tasks/{id}/approve", id)
            .header(HttpHeaders.AUTHORIZATION,admin)
            .contentType(MediaType.APPLICATION_JSON).content("{\"confirmation\":\"YES\"}"))
            .andExpect(status().isBadRequest());
        verify(gateway, never()).generate(any());

        mvc.perform(post("/api/ai/agent/tasks/{id}/approve", id)
            .header(HttpHeaders.AUTHORIZATION,admin)
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"confirmation\":\"APPROVE_AGENT_TASK\"}"))
            .andExpect(status().isAccepted());
        mvc.perform(post("/api/ai/agent/tasks/{id}/approve", id)
            .header(HttpHeaders.AUTHORIZATION,admin)
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"confirmation\":\"APPROVE_AGENT_TASK\"}"))
            .andExpect(status().isConflict());
        long owner = users.findByUsername("admin").orElseThrow().id();
        for (int i=0;i<50;i++) {
            if (store.find(owner,id).orElseThrow().status().equals("COMPLETED")) break;
            Thread.sleep(20);
        }
        assertThat(store.find(owner,id).orElseThrow().status()).isEqualTo("COMPLETED");
        assertThat(store.find(owner,id).orElseThrow().result()).isEqualTo("Written plan only");
        assertThat(store.find(owner,id).orElseThrow().approvedBy()).isEqualTo(owner);
        verify(gateway, times(1)).generate(any(AgentTaskStore.AgentTask.class));
        mvc.perform(get("/api/ai/agent/capabilities").header(HttpHeaders.AUTHORIZATION,admin))
            .andExpect(status().isOk()).andExpect(jsonPath("$.data.codexEnabled").value(false));
    }

    @Test void regularUserCannotAccessTaskApiOrAdminGateway() throws Exception {
        String admin = login("admin", "matrix-prp");
        String code = json.readTree(mvc.perform(post("/api/auth/invitations")
            .header(HttpHeaders.AUTHORIZATION,admin)).andExpect(status().isOk())
            .andReturn().getResponse().getContentAsString()).path("data").path("code").asText();
        mvc.perform(post("/api/auth/register").contentType(MediaType.APPLICATION_JSON)
            .content(json.writeValueAsString(Map.of("username","agent_denied_user","password","test-friend-password",
                "displayName","Restricted","invitationCode",code)))).andExpect(status().isOk());
        String guest = login("agent_denied_user", "test-friend-password");
        String id = create(admin,"ANALYZE","Review my plan");
        mvc.perform(get("/api/ai/agent/capabilities").header(HttpHeaders.AUTHORIZATION,guest))
            .andExpect(status().isForbidden());
        mvc.perform(get("/api/ai/agent/tasks").header(HttpHeaders.AUTHORIZATION,guest))
            .andExpect(status().isForbidden());
        mvc.perform(get("/api/ai/agent/tasks/{id}",id).header(HttpHeaders.AUTHORIZATION,guest))
            .andExpect(status().isForbidden());
        mvc.perform(post("/api/ai/agent/tasks/{id}/approve",id)
            .header(HttpHeaders.AUTHORIZATION,guest).contentType(MediaType.APPLICATION_JSON)
            .content("{\"confirmation\":\"APPROVE_AGENT_TASK\"}"))
            .andExpect(status().isForbidden());
        mvc.perform(post("/api/ai/agent/tasks").header(HttpHeaders.AUTHORIZATION,guest)
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"taskType\":\"PLAN\",\"prompt\":\"Run a command\"}"))
            .andExpect(status().isForbidden());
        mvc.perform(get("/api/ai/agent/tasks")).andExpect(status().isUnauthorized());
        verify(gateway, never()).generate(any());
    }

    @Test void invalidTypesAndCancelFlowFailClosed() throws Exception {
        String admin = login("admin", "matrix-prp");
        mvc.perform(post("/api/ai/agent/tasks").header(HttpHeaders.AUTHORIZATION,admin)
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"taskType\":\"EXEC\",\"prompt\":\"run shell\"}"))
            .andExpect(status().isBadRequest());
        String id = create(admin,"SUMMARIZE","Summarize this work");
        mvc.perform(post("/api/ai/agent/tasks/{id}/cancel",id)
            .header(HttpHeaders.AUTHORIZATION,admin)).andExpect(status().isOk())
            .andExpect(jsonPath("$.data.status").value("CANCELLED"));
        mvc.perform(post("/api/ai/agent/tasks/{id}/approve",id)
            .header(HttpHeaders.AUTHORIZATION,admin).contentType(MediaType.APPLICATION_JSON)
            .content("{\"confirmation\":\"APPROVE_AGENT_TASK\"}"))
            .andExpect(status().isConflict());
        verify(gateway, never()).generate(any());
    }
}
