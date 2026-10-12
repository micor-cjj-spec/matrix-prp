package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.ai.DeepSeekClient;
import com.matrix.prp.practice.PracticeModels;
import com.matrix.prp.practice.PracticeService;
import com.matrix.prp.wellness.WellnessModels;
import com.matrix.prp.wellness.WellnessService;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
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

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class AiBusinessContextTests {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @MockitoBean DeepSeekClient deepSeek;
    @MockitoBean PracticeService practice;
    @MockitoBean WellnessService wellness;
    private final AtomicReference<List<DeepSeekClient.ChatMessage>> observed = new AtomicReference<>();

    private String login(String name, String password) throws Exception {
        String output = mvc.perform(post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
            .content(json.writeValueAsString(Map.of("username",name,"password",password))))
            .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        return json.readTree(output).path("data").path("token").asText();
    }
    private String bearer(String token) { return "Bearer " + token; }
    private void task(String token, String title) throws Exception {
        mvc.perform(post("/api/tasks").header(HttpHeaders.AUTHORIZATION,bearer(token))
            .contentType(MediaType.APPLICATION_JSON)
            .content(json.writeValueAsString(Map.of("moduleCode","learning",
                "title",title, "description","NOT FOR MODEL CONTEXT", "dueDate", LocalDate.now().toString()))))
            .andExpect(status().isOk());
    }
    @BeforeEach
    @SuppressWarnings("unchecked")
    void stub() throws Exception {
        observed.set(null);
        when(deepSeek.model()).thenReturn("deepseek-chat");
        when(deepSeek.stream(anyList(), anyInt(), any())).thenAnswer(invocation -> {
            observed.set(List.copyOf(invocation.getArgument(0)));
            Consumer<String> send = invocation.getArgument(2);
            send.accept("Context answer");
            return new DeepSeekClient.Result("Context answer", 120, 18);
        });
        when(practice.statistics()).thenReturn(new PracticeModels.Statistics(10,7,3));
        when(wellness.daily(any(LocalDate.class))).thenAnswer(invocation -> new WellnessModels.DailySummary(
            invocation.getArgument(0), new BigDecimal("1900"), new BigDecimal("90"),
            new BigDecimal("205"), new BigDecimal("55"), 3, 40,
            new BigDecimal("140"), new BigDecimal("70"), null, List.of("breakfast","dinner")));
    }

    @Test void defaultsToNoBusinessAccessAndRequiresExplicitOneTimeConsent() throws Exception {
        String admin = login("admin","matrix-prp");
        mvc.perform(post("/api/ai/context/preview").contentType(MediaType.APPLICATION_JSON)
            .content("{\"scopes\":[\"tasks\"]}")).andExpect(status().isUnauthorized());
        mvc.perform(post("/api/ai/context/preview").header(HttpHeaders.AUTHORIZATION,bearer(admin))
            .contentType(MediaType.APPLICATION_JSON).content("{\"scopes\":[\"finance\"]}"))
            .andExpect(status().isBadRequest());
        mvc.perform(post("/api/ai/context/preview").header(HttpHeaders.AUTHORIZATION,bearer(admin))
            .contentType(MediaType.APPLICATION_JSON).content("{\"scopes\":[\"tasks\",\"tasks\"]}"))
            .andExpect(status().isBadRequest());
        mvc.perform(post("/api/ai/chat/stream").header(HttpHeaders.AUTHORIZATION,bearer(admin))
            .contentType(MediaType.APPLICATION_JSON).content("{\"content\":\"test\",\"contextScopes\":[\"tasks\"]}"))
            .andExpect(status().isBadRequest());

        MvcResult plain = mvc.perform(post("/api/ai/chat/stream")
            .header(HttpHeaders.AUTHORIZATION,bearer(admin)).contentType(MediaType.APPLICATION_JSON)
            .content("{\"content\":\"No personal data\"}"))
            .andExpect(request().asyncStarted()).andReturn();
        mvc.perform(asyncDispatch(plain)).andExpect(status().isOk());
        assertThat(observed.get().getLast().content()).isEqualTo("No personal data");
        verify(practice, never()).statistics();
        verify(wellness, never()).daily(any(LocalDate.class));
    }

    @Test void previewAndChatReturnOnlyAuthenticatedUsersMinimizedScopes() throws Exception {
        String admin = login("admin","matrix-prp");
        String code = json.readTree(mvc.perform(post("/api/auth/invitations")
            .header(HttpHeaders.AUTHORIZATION,bearer(admin))).andExpect(status().isOk())
            .andReturn().getResponse().getContentAsString()).path("data").path("code").asText();
        mvc.perform(post("/api/auth/register").contentType(MediaType.APPLICATION_JSON)
            .content(json.writeValueAsString(Map.of("username","context_friend",
                "password","test-context-pw","displayName","Context Friend",
                "invitationCode",code)))).andExpect(status().isOk());
        String friend = login("context_friend","test-context-pw");
        task(admin,"Private admin project");
        task(friend,"Friend learning task");

        String preview = mvc.perform(post("/api/ai/context/preview")
            .header(HttpHeaders.AUTHORIZATION,bearer(friend)).contentType(MediaType.APPLICATION_JSON)
            .content("{\"scopes\":[\"tasks\",\"practice\",\"wellness\"]}"))
            .andExpect(status().isOk()).andExpect(header().string(HttpHeaders.CACHE_CONTROL,"no-store"))
            .andExpect(jsonPath("$.data.data.practice.correct").value(7))
            .andExpect(jsonPath("$.data.data.wellness.exerciseMinutes").value(40))
            .andReturn().getResponse().getContentAsString();
        assertThat(preview).contains("Friend learning task")
            .doesNotContain("Private admin project").doesNotContain("NOT FOR MODEL CONTEXT")
            .doesNotContain("latestWeightKg");

        MvcResult streamed = mvc.perform(post("/api/ai/chat/stream")
            .header(HttpHeaders.AUTHORIZATION,bearer(friend)).contentType(MediaType.APPLICATION_JSON)
            .content("{\"content\":\"How am I doing?\",\"contextConsent\":true,\"contextScopes\":[\"tasks\",\"practice\",\"wellness\"]}"))
            .andExpect(request().asyncStarted()).andReturn();
        mvc.perform(asyncDispatch(streamed)).andExpect(status().isOk());
        String outbound = observed.get().getLast().content();
        assertThat(outbound).contains("Friend learning task", "How am I doing?", "exerciseMinutes", "attempted")
            .doesNotContain("Private admin project").doesNotContain("NOT FOR MODEL CONTEXT")
            .doesNotContain("latestWeightKg");
        // The business snapshot is only for the upstream request, not stored as a user message.
        JsonNode conversations = json.readTree(mvc.perform(get("/api/ai/conversations")
            .header(HttpHeaders.AUTHORIZATION,bearer(friend)))
            .andExpect(status().isOk()).andReturn().getResponse().getContentAsString()).path("data");
        String id = conversations.get(0).path("id").asText();
        String history = mvc.perform(get("/api/ai/conversations/{id}/messages",id)
            .header(HttpHeaders.AUTHORIZATION,bearer(friend))).andExpect(status().isOk())
            .andReturn().getResponse().getContentAsString();
        assertThat(history).contains("How am I doing?").doesNotContain("Friend learning task");

        MvcResult next = mvc.perform(post("/api/ai/chat/stream")
            .header(HttpHeaders.AUTHORIZATION,bearer(friend)).contentType(MediaType.APPLICATION_JSON)
            .content("{\"content\":\"Another question\"}"))
            .andExpect(request().asyncStarted()).andReturn();
        mvc.perform(asyncDispatch(next)).andExpect(status().isOk());
        assertThat(observed.get().getLast().content()).isEqualTo("Another question");
    }
}
