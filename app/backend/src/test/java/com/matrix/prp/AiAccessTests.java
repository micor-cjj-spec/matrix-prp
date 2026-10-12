package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.ai.AiStore;
import com.matrix.prp.ai.DeepSeekClient;
import com.matrix.prp.auth.repository.UserStore;
import java.util.Map;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Consumer;
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
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.web.server.ResponseStatusException;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class AiAccessTests {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired AiStore store;
    @Autowired UserStore users;
    @MockitoBean DeepSeekClient deepSeek;
    private final AtomicReference<List<DeepSeekClient.ChatMessage>> outbound = new AtomicReference<>();

    @BeforeEach
    @SuppressWarnings("unchecked")
    void stubDeepSeek() throws Exception {
        when(deepSeek.model()).thenReturn("deepseek-chat");
        outbound.set(null);
        when(deepSeek.stream(anyList(), anyInt(), any())).thenAnswer(invocation -> {
            outbound.set(List.copyOf(invocation.getArgument(0)));
            Consumer<String> delta = invocation.getArgument(2);
            delta.accept("AI test response");
            return new DeepSeekClient.Result("AI test response", 16, 4);
        });
    }

    private String login(String name, String password) throws Exception {
        String body = json.writeValueAsString(Map.of("username", name, "password", password));
        String response = mvc.perform(post("/api/auth/login").contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        return json.readTree(response).path("data").path("token").asText();
    }

    @Test
    void historyAndCodexStubAreTenantRestricted() throws Exception {
        String admin = login("admin", "matrix-prp");
        String code = json.readTree(mvc.perform(post("/api/auth/invitations")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + admin))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString())
                .path("data").path("code").asText();
        mvc.perform(post("/api/auth/register").contentType(MediaType.APPLICATION_JSON)
                .content(json.writeValueAsString(Map.of("username", "ai_friend", "password", "test-friend-password",
                        "displayName", "AI Friend", "invitationCode", code)))).andExpect(status().isOk());
        String friend = login("ai_friend", "test-friend-password");
        long owner = users.findByUsername("admin").orElseThrow().id();
        String conversation = store.create(owner, "Admin secrets").id();
        store.append(owner, conversation, "user", "Private note");
        mvc.perform(get("/api/ai/conversations/{id}/messages", conversation)
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + friend)).andExpect(status().isNotFound());
        mvc.perform(get("/api/ai/conversations")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + friend))
                .andExpect(jsonPath("$.data.length()").value(0));
        mvc.perform(get("/api/ai/codex/capabilities")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + friend)).andExpect(status().isForbidden());
        mvc.perform(get("/api/ai/codex/capabilities")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + admin))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.enabled").value(false));

        String job = "{\"taskType\":\"CODE_REVIEW\",\"target\":\"matrix-prp\"}";
        mvc.perform(post("/api/ai/codex/jobs").contentType(MediaType.APPLICATION_JSON).content(job)
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + friend)).andExpect(status().isForbidden());
        mvc.perform(post("/api/ai/codex/jobs").contentType(MediaType.APPLICATION_JSON).content(job)
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + admin)).andExpect(status().isServiceUnavailable());
        mvc.perform(get("/api/ai/usage")).andExpect(status().isUnauthorized());
    }

    @Test
    void streamsChatAndTracksConservativeAllowance() throws Exception {
        String admin = login("admin", "matrix-prp");
        MvcResult result = mvc.perform(post("/api/ai/chat/stream")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + admin)
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.TEXT_EVENT_STREAM)
                .content("{\"content\":\"Hello AI\"}"))
                .andExpect(request().asyncStarted()).andReturn();
        mvc.perform(asyncDispatch(result)).andExpect(status().isOk());
        String output = result.getResponse().getContentAsString();
        assertThat(output).contains("AI test response").contains("event:done");
        assertThat(outbound.get().getFirst().role()).isEqualTo("system");
        assertThat(outbound.get().getFirst().content()).contains("PRP 助手", "Matrix PRP");
        assertThat(outbound.get().getLast().content()).isEqualTo("Hello AI");
        assertThat(store.list(users.findByUsername("admin").orElseThrow().id())).isNotEmpty();
        assertThat(store.usage(users.findByUsername("admin").orElseThrow().id(),
                java.time.YearMonth.now(java.time.ZoneOffset.UTC).toString()).requests()).isGreaterThan(0);
    }

    @Test
    void reservationIsAtomicAndFailsClosedAtLimit() {
        long user = 99999L;
        store.reserve(user, "2099-10", 100, 1, 120, 10, 1000);
        assertThatThrownBy(() -> store.reserve(user, "2099-10", 100, 1, 120, 10, 1000))
                .isInstanceOf(ResponseStatusException.class);
    }
}
