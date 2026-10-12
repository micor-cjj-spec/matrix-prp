package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.ai.AiKeyCipher;
import com.matrix.prp.ai.AiProviderClient;
import com.matrix.prp.ai.AiSettingsService;
import com.matrix.prp.ai.AiSettingsStore;
import com.matrix.prp.ai.DeepSeekClient;
import com.matrix.prp.auth.repository.UserStore;
import java.util.Map;
import java.util.function.Consumer;
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

@SpringBootTest(properties = "matrix-prp.ai.key-encryption-secret=MDEyMzQ1Njc4OUFCQ0RFRjAxMjM0NTY3ODlBQkNERUY=")
@AutoConfigureMockMvc
@ActiveProfiles("test")
class AiProviderSettingsTests {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired UserStore users;
    @Autowired AiSettingsStore settingsStore;
    @Autowired AiKeyCipher cipher;
    @MockitoBean AiProviderClient providerClient;

    private String login(String username, String password) throws Exception {
        return json.readTree(mvc.perform(post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
            .content(json.writeValueAsString(Map.of("username", username, "password", password))))
            .andExpect(status().isOk()).andReturn().getResponse().getContentAsString())
            .path("data").path("token").asText();
    }
    private String bearer(String token) { return "Bearer " + token; }

    @Test
    void encryptedKeysNeverReturnAndTenantIsolationHolds() throws Exception {
        String admin = login("admin", "matrix-prp");
        String key = "sk-sensitive-test-value";
        String body = json.writeValueAsString(Map.of("apiKey", key));
        String output = mvc.perform(put("/api/ai/settings/providers/qwen/key")
            .header(HttpHeaders.AUTHORIZATION, bearer(admin))
            .contentType(MediaType.APPLICATION_JSON).content(body))
            .andExpect(status().isOk()).andExpect(header().string(HttpHeaders.CACHE_CONTROL, "no-store"))
            .andExpect(jsonPath("$.data.providers[5].personalKey").value(true))
            .andReturn().getResponse().getContentAsString();
        assertThat(output).doesNotContain(key).doesNotContain("encryptedApiKey");
        long owner = users.findByUsername("admin").orElseThrow().id();
        String cipherText = settingsStore.encryptedKeys(owner).get("qwen");
        assertThat(cipherText).isNotEqualTo(key);
        assertThat(cipher.decrypt(owner, "qwen", cipherText)).isEqualTo(key);
        assertThatThrownBy(() -> cipher.decrypt(owner + 1, "qwen", cipherText)).isInstanceOf(Exception.class);
        assertThatThrownBy(() -> cipher.decrypt(owner, "deepseek", cipherText)).isInstanceOf(Exception.class);

        String code = json.readTree(mvc.perform(post("/api/auth/invitations")
            .header(HttpHeaders.AUTHORIZATION, bearer(admin))).andExpect(status().isOk())
            .andReturn().getResponse().getContentAsString()).path("data").path("code").asText();
        mvc.perform(post("/api/auth/register").contentType(MediaType.APPLICATION_JSON)
            .content(json.writeValueAsString(Map.of("username", "provider_friend", "password", "friend-pw-123456",
                "displayName", "Friend", "invitationCode", code)))).andExpect(status().isOk());
        String friend = login("provider_friend", "friend-pw-123456");
        mvc.perform(get("/api/ai/settings").header(HttpHeaders.AUTHORIZATION, bearer(friend)))
            .andExpect(jsonPath("$.data.providers[5].personalKey").value(false));
        mvc.perform(put("/api/ai/settings/selection").header(HttpHeaders.AUTHORIZATION, bearer(friend))
            .contentType(MediaType.APPLICATION_JSON).content("{\"provider\":\"qwen\",\"model\":\"qwen-plus\"}"))
            .andExpect(status().isOk());
        String ownerSettings = mvc.perform(get("/api/ai/settings")
            .header(HttpHeaders.AUTHORIZATION, bearer(admin)))
            .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        assertThat(json.readTree(ownerSettings).path("data").path("selectedProvider").asText()).isNotEqualTo("qwen");
        mvc.perform(get("/api/ai/settings")).andExpect(status().isUnauthorized());
    }

    @Test
    @SuppressWarnings("unchecked")
    void modelSelectionAndConnectionTestUsesSelectedPersonalKey() throws Exception {
        String admin = login("admin", "matrix-prp");
        mvc.perform(put("/api/ai/settings/providers/claude/key")
            .header(HttpHeaders.AUTHORIZATION, bearer(admin))
            .contentType(MediaType.APPLICATION_JSON).content("{\"apiKey\":\"sk-test-claude\"}"))
            .andExpect(status().isOk());
        mvc.perform(put("/api/ai/settings/selection").header(HttpHeaders.AUTHORIZATION, bearer(admin))
            .contentType(MediaType.APPLICATION_JSON).content("{\"provider\":\"claude\",\"model\":\"claude-sonnet-4-5\"}"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.data.selectedProvider").value("claude"));
        when(providerClient.stream(any(), anyList(), anyInt(), any())).thenAnswer(invocation -> {
            AiSettingsService.Runtime runtime = invocation.getArgument(0);
            assertThat(runtime.apiKey()).isEqualTo("sk-test-claude");
            assertThat(runtime.provider().anthropic()).isTrue();
            Consumer<String> delta = invocation.getArgument(3);
            delta.accept("OK");
            return new DeepSeekClient.Result("OK", 12, 3);
        });
        mvc.perform(post("/api/ai/settings/providers/claude/test")
            .header(HttpHeaders.AUTHORIZATION, bearer(admin)).contentType(MediaType.APPLICATION_JSON)
            .content("{\"provider\":\"claude\",\"model\":\"claude-sonnet-4-5\"}"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.data.connected").value(true));
        mvc.perform(put("/api/ai/settings/selection").header(HttpHeaders.AUTHORIZATION, bearer(admin))
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"provider\":\"untrusted\",\"model\":\"abc\"}")).andExpect(status().isBadRequest());
        mvc.perform(put("/api/ai/settings/selection").header(HttpHeaders.AUTHORIZATION, bearer(admin))
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"provider\":\"qwen\",\"model\":\"invalid model\\n\"}")).andExpect(status().isBadRequest());
    }

    @Test
    void refusesMissingEncryptionMasterKey() {
        AiKeyCipher noKey = new AiKeyCipher("");
        assertThatThrownBy(() -> noKey.encrypt(1, "qwen", "secret")).isInstanceOf(Exception.class);
    }
}
