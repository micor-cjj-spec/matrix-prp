package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.repository.UserStore;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class MultiUserIsolationTests {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;
    @Autowired UserStore users;

    private JsonNode send(String path, String token, String body) throws Exception {
        MockHttpServletRequestBuilder request = post(path).contentType(MediaType.APPLICATION_JSON).content(body);
        if (token != null) request.header(HttpHeaders.AUTHORIZATION, "Bearer " + token);
        return mapper.readTree(mvc.perform(request).andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString()).path("data");
    }

    private String login(String username, String password) throws Exception {
        return send("/api/auth/login", null, mapper.writeValueAsString(
                Map.of("username", username, "password", password))).path("token").asText();
    }

    private MockHttpServletRequestBuilder authenticated(MockHttpServletRequestBuilder request, String token) {
        return request.header(HttpHeaders.AUTHORIZATION, "Bearer " + token);
    }

    @Test
    void invitedAccountsCannotSeeOrModifyOtherPeoplesData() throws Exception {
        String admin = login("admin", "matrix-prp");
        String invite = send("/api/auth/invitations", admin, "{}").path("code").asText();
        String password = "friend-test-password-2026";
        String friend = send("/api/auth/register", null, mapper.writeValueAsString(Map.of(
                "username", "friend_p0_case", "password", password, "displayName", "Friend",
                "invitationCode", invite))).path("token").asText();
        assertThat(users.findByUsername("friend_p0_case").orElseThrow().passwordHash())
                .isNotEqualTo(password).startsWith("$2");

        mvc.perform(post("/api/auth/register").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(Map.of("username", "another_friend",
                        "password", password, "displayName", "Another", "invitationCode", invite))))
                .andExpect(status().isBadRequest());
        mvc.perform(authenticated(post("/api/auth/invitations"), friend)).andExpect(status().isForbidden());
        mvc.perform(authenticated(get("/api/knowledge/tree"), friend)).andExpect(status().isForbidden());
        mvc.perform(authenticated(get("/api/users/me"), friend)).andExpect(status().isOk())
                .andExpect(jsonPath("$.data.username").value("friend_p0_case"));

        String task = "{\"moduleCode\":\"work\",\"title\":\"Admin private task\"}";
        String record = "{\"moduleCode\":\"life\",\"title\":\"Private record\",\"content\":\"secret\"}";
        String finance = "{\"type\":\"expense\",\"amount\":31.50,\"category\":\"food\"}";
        long taskId = send("/api/tasks", admin, task).path("id").asLong();
        long recordId = send("/api/records", admin, record).path("id").asLong();
        long transactionId = send("/api/finance/transactions", admin, finance).path("id").asLong();

        for (String path : new String[]{"/api/tasks", "/api/records", "/api/finance/transactions"}) {
            mvc.perform(authenticated(get(path), friend)).andExpect(status().isOk())
                    .andExpect(jsonPath("$.data.length()").value(0));
        }
        mvc.perform(authenticated(get("/api/dashboard/summary"), friend)).andExpect(status().isOk())
                .andExpect(jsonPath("$.data.recordCount").value(0));
        mvc.perform(authenticated(put("/api/tasks/{id}", taskId)
                .contentType(MediaType.APPLICATION_JSON).content(task), friend)).andExpect(status().isNotFound());
        mvc.perform(authenticated(delete("/api/tasks/{id}", taskId), friend)).andExpect(status().isNotFound());
        mvc.perform(authenticated(put("/api/records/{id}", recordId)
                .contentType(MediaType.APPLICATION_JSON).content(record), friend)).andExpect(status().isNotFound());
        mvc.perform(authenticated(delete("/api/records/{id}", recordId), friend)).andExpect(status().isNotFound());
        mvc.perform(authenticated(put("/api/finance/transactions/{id}", transactionId)
                .contentType(MediaType.APPLICATION_JSON).content(finance), friend)).andExpect(status().isNotFound());
        mvc.perform(authenticated(delete("/api/finance/transactions/{id}", transactionId), friend))
                .andExpect(status().isNotFound());

        long friendTask = send("/api/tasks", friend,
                "{\"moduleCode\":\"work\",\"title\":\"Friend task\"}").path("id").asLong();
        mvc.perform(authenticated(delete("/api/tasks/{id}", friendTask), admin)).andExpect(status().isNotFound());
        mvc.perform(authenticated(get("/api/tasks"), friend)).andExpect(status().isOk())
                .andExpect(jsonPath("$.data[?(@.title == 'Friend task')]").exists());
        mvc.perform(authenticated(get("/api/tasks"), admin)).andExpect(status().isOk())
                .andExpect(jsonPath("$.data[?(@.title == 'Admin private task')]").exists());
    }
}
