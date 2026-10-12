package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.ai.CodexJobStore;
import com.matrix.prp.ai.CodexWorkflowClient;
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
class CodexJobAccessTests {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired CodexJobStore store;
    @Autowired UserStore users;
    @MockitoBean CodexWorkflowClient workflow;

    @BeforeEach void enabledMock() {
        when(workflow.configured()).thenReturn(true);
    }
    private String login(String name,String pass) throws Exception {
        String response=mvc.perform(post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
            .content(json.writeValueAsString(Map.of("username",name,"password",pass))))
            .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        return "Bearer "+json.readTree(response).path("data").path("token").asText();
    }
    private String create(String token,String type,String description) throws Exception {
        String body=json.writeValueAsString(Map.of("taskType",type,"prompt",description));
        String jsonResponse=mvc.perform(post("/api/ai/codex/requests")
            .header(HttpHeaders.AUTHORIZATION,token).contentType(MediaType.APPLICATION_JSON).content(body))
            .andExpect(status().isCreated()).andExpect(header().string(HttpHeaders.CACHE_CONTROL,"no-store"))
            .andReturn().getResponse().getContentAsString();
        return json.readTree(jsonResponse).path("data").path("id").asText();
    }

    @Test void approvedOnceAndDispatchWithoutAutomaticMerge() throws Exception {
        String admin=login("admin","matrix-prp");
        String id=create(admin,"FIX","Fix input validation in web form");
        mvc.perform(get("/api/ai/codex/requests/{id}",id)
            .header(HttpHeaders.AUTHORIZATION,admin))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.job.status").value("PENDING_APPROVAL"));
        verify(workflow,never()).dispatch(any());

        mvc.perform(post("/api/ai/codex/requests/{id}/approve",id)
            .header(HttpHeaders.AUTHORIZATION,admin).contentType(MediaType.APPLICATION_JSON)
            .content("{\"confirmation\":\"OK\"}")).andExpect(status().isBadRequest());
        verify(workflow,never()).dispatch(any());

        mvc.perform(post("/api/ai/codex/requests/{id}/approve",id)
            .header(HttpHeaders.AUTHORIZATION,admin).contentType(MediaType.APPLICATION_JSON)
            .content("{\"confirmation\":\"APPROVE_CODEX_JOB\"}")).andExpect(status().isAccepted());
        mvc.perform(post("/api/ai/codex/requests/{id}/approve",id)
            .header(HttpHeaders.AUTHORIZATION,admin).contentType(MediaType.APPLICATION_JSON)
            .content("{\"confirmation\":\"APPROVE_CODEX_JOB\"}")).andExpect(status().isConflict());
        long owner=users.findByUsername("admin").orElseThrow().id();
        for (int i=0;i<100;i++) {
            if(store.find(owner,id).orElseThrow().status().equals("DISPATCHED")) break;
            Thread.sleep(20);
        }
        assertThat(store.find(owner,id).orElseThrow().status()).isEqualTo("DISPATCHED");
        assertThat(store.find(owner,id).orElseThrow().approvedBy()).isEqualTo(owner);
        verify(workflow,times(1)).dispatch(any());
        mvc.perform(get("/api/ai/codex/requests/capabilities")
            .header(HttpHeaders.AUTHORIZATION,admin))
            .andExpect(status().isOk()).andExpect(jsonPath("$.data.enabled").value(true));
        mvc.perform(post("/api/ai/codex/jobs").header(HttpHeaders.AUTHORIZATION,admin)
            .contentType(MediaType.APPLICATION_JSON).content("{\"taskType\":\"FIX\",\"target\":\"matrix-prp\"}"))
            .andExpect(status().isServiceUnavailable()); // Old endpoint stays disabled.
    }
    @Test void ordinaryUsersHaveNoAccessAndNoOtherUserVisibility() throws Exception {
        String admin=login("admin","matrix-prp");
        String code=json.readTree(mvc.perform(post("/api/auth/invitations")
            .header(HttpHeaders.AUTHORIZATION,admin)).andExpect(status().isOk())
            .andReturn().getResponse().getContentAsString()).path("data").path("code").asText();
        mvc.perform(post("/api/auth/register").contentType(MediaType.APPLICATION_JSON)
            .content(json.writeValueAsString(Map.of("username","codex_p4_friend","password","test-friend-password",
                "displayName","Friend","invitationCode",code)))).andExpect(status().isOk());
        String friend=login("codex_p4_friend","test-friend-password");
        String id=create(admin,"TESTS","Test the backend");
        mvc.perform(get("/api/ai/codex/requests")
            .header(HttpHeaders.AUTHORIZATION,friend)).andExpect(status().isForbidden());
        mvc.perform(get("/api/ai/codex/requests/{id}",id)
            .header(HttpHeaders.AUTHORIZATION,friend)).andExpect(status().isForbidden());
        mvc.perform(get("/api/ai/codex/requests/capabilities")
            .header(HttpHeaders.AUTHORIZATION,friend)).andExpect(status().isForbidden());
        mvc.perform(post("/api/ai/codex/requests")
            .header(HttpHeaders.AUTHORIZATION,friend).contentType(MediaType.APPLICATION_JSON)
            .content("{\"taskType\":\"FIX\",\"prompt\":\"fix bug\"}")).andExpect(status().isForbidden());
        mvc.perform(post("/api/ai/codex/requests/{id}/approve",id)
            .header(HttpHeaders.AUTHORIZATION,friend).contentType(MediaType.APPLICATION_JSON)
            .content("{\"confirmation\":\"APPROVE_CODEX_JOB\"}")).andExpect(status().isForbidden());
        mvc.perform(get("/api/ai/codex/requests")).andExpect(status().isUnauthorized());
        verify(workflow,never()).dispatch(any());
    }
    @Test void rejectsUnsupportedWorkAndCancelledRequests() throws Exception {
        String admin=login("admin","matrix-prp");
        mvc.perform(post("/api/ai/codex/requests")
            .header(HttpHeaders.AUTHORIZATION,admin).contentType(MediaType.APPLICATION_JSON)
            .content("{\"taskType\":\"DEPLOY\",\"prompt\":\"production\"}")).andExpect(status().isBadRequest());
        String id=create(admin,"IMPLEMENT","Add validation tests");
        mvc.perform(post("/api/ai/codex/requests/{id}/cancel",id)
            .header(HttpHeaders.AUTHORIZATION,admin))
            .andExpect(status().isOk()).andExpect(jsonPath("$.data.status").value("CANCELLED"));
        mvc.perform(post("/api/ai/codex/requests/{id}/approve",id)
            .header(HttpHeaders.AUTHORIZATION,admin).contentType(MediaType.APPLICATION_JSON)
            .content("{\"confirmation\":\"APPROVE_CODEX_JOB\"}")).andExpect(status().isConflict());
        verify(workflow,never()).dispatch(any());
    }
}
