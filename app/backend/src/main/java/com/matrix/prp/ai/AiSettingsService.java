package com.matrix.prp.ai;

import com.matrix.prp.auth.security.CurrentUser;
import java.time.YearMonth;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class AiSettingsService {
    public record ProviderInfo(String id, String name, List<String> models, String defaultModel,
                               boolean configured, boolean personalKey) {}
    public record Settings(String selectedProvider, String selectedModel, List<ProviderInfo> providers) {}
    /** Never expose this internal record through an HTTP controller. */
    public record Runtime(AiProviderCatalog.Provider provider, String model, String apiKey, boolean legacy) {}
    private final AiSettingsStore store;
    private final AiKeyCipher cipher;
    private final AiProviderClient client;
    private final AiStore usage;
    private final String legacyDeepSeekKey;
    private final String legacyModel;
    private final int userRequests, globalRequests;
    private final long userTokens, globalTokens;

    public AiSettingsService(AiSettingsStore store, AiKeyCipher cipher, AiProviderClient client, AiStore usage,
        @Value("${matrix-prp.ai.deepseek.api-key:}") String legacyDeepSeekKey,
        @Value("${matrix-prp.ai.deepseek.model:deepseek-chat}") String legacyModel,
        @Value("${matrix-prp.ai.user-monthly-requests:200}") int userRequests,
        @Value("${matrix-prp.ai.global-monthly-requests:1000}") int globalRequests,
        @Value("${matrix-prp.ai.user-monthly-reserved-tokens:250000}") long userTokens,
        @Value("${matrix-prp.ai.global-monthly-reserved-tokens:1000000}") long globalTokens) {
        this.store = store; this.cipher = cipher; this.client = client; this.usage = usage;
        this.legacyDeepSeekKey = legacyDeepSeekKey; this.legacyModel = legacyModel;
        this.userRequests = userRequests; this.globalRequests = globalRequests;
        this.userTokens = userTokens; this.globalTokens = globalTokens;
    }
    public Settings settings() {
        long user = CurrentUser.id();
        AiSettingsStore.Selection selected = selection(user);
        Map<String, String> keys = store.encryptedKeys(user);
        List<ProviderInfo> providers = AiProviderCatalog.PROVIDERS.stream().map(p -> {
            boolean personal = keys.containsKey(p.id());
            boolean legacy = p.id().equals("deepseek") && legacyDeepSeekKey != null && !legacyDeepSeekKey.isBlank();
            return new ProviderInfo(p.id(), p.name(), p.models(), p.defaultModel(), personal || legacy, personal);
        }).toList();
        return new Settings(selected.provider(), selected.model(), providers);
    }
    public AiSettingsStore.Selection selection(long user) {
        return store.selection(user).orElse(new AiSettingsStore.Selection(
            "deepseek", AiProviderCatalog.validateModel(legacyModel)));
    }
    public boolean hasPersonalKey(long user, String provider) {
        return store.encryptedKeys(user).containsKey(provider);
    }
    public Runtime resolve(long user) {
        AiSettingsStore.Selection selected = selection(user);
        return resolve(user, selected.provider(), selected.model());
    }
    public Runtime resolve(long user, String id, String model) {
        AiProviderCatalog.Provider provider = AiProviderCatalog.require(id);
        AiProviderCatalog.validateModel(model);
        String encoded = store.encryptedKeys(user).get(id);
        if (encoded != null) return new Runtime(provider, model, cipher.decrypt(user, id, encoded), false);
        if (id.equals("deepseek") && legacyDeepSeekKey != null && !legacyDeepSeekKey.isBlank())
            return new Runtime(provider, model, legacyDeepSeekKey, true);
        throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "Selected AI provider has no API key");
    }
    public Settings saveKey(String id, String apiKey) {
        long user = CurrentUser.id();
        AiProviderCatalog.require(id);
        if (apiKey == null || apiKey.isBlank() || apiKey.length() > 1024 || apiKey.contains("\n")
                || apiKey.contains("\r"))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid API key");
        store.putKey(user, id, cipher.encrypt(user, id, apiKey.trim()));
        return settings();
    }
    public Settings removeKey(String id) {
        AiProviderCatalog.require(id);
        store.deleteKey(CurrentUser.id(), id);
        return settings();
    }
    public Settings choose(String id, String model) {
        long user = CurrentUser.id();
        AiProviderCatalog.require(id);
        store.select(user, id, AiProviderCatalog.validateModel(model));
        return settings();
    }
    /** Real, metered minimal upstream request; test cannot bypass configured monthly quota. */
    public Map<String, Object> test(String provider, String model) {
        long user = CurrentUser.id();
        Runtime config = resolve(user, provider, model);
        String month = YearMonth.now(ZoneOffset.UTC).toString();
        usage.reserve(user, month, 2048, userRequests, userTokens, globalRequests, globalTokens);
        try {
            DeepSeekClient.Result result = client.stream(config,
                List.of(new DeepSeekClient.ChatMessage("user", "Reply with OK.")), 16, s -> {});
            usage.completed(user, month, result.inputTokens(), result.outputTokens());
            return Map.of("connected", true, "provider", provider, "model", model);
        } catch (Exception ex) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,
                "Connection test failed; check model, key or provider quota");
        }
    }
}
