package com.matrix.prp.ai;

import java.util.List;
import java.util.Objects;
import java.util.function.Consumer;
import com.matrix.prp.auth.security.CurrentUser;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** Compatibility adapter: preserves the pre-existing DeepSeek and provider stream parsers. */
@Component
public class DefaultAiModelGateway implements AiModelGateway {
    private final DeepSeekClient legacy;
    private final AiProviderClient providers;
    private final SpringAiDeepSeekAdapter springAi;
    private final SpringAiUniversalProviderAdapter universal;
    private final boolean springAiEnabled;
    private final long springAiCanaryUser;

    /** Backward compatible direct construction for older tests: original transport. */
    public DefaultAiModelGateway(DeepSeekClient legacy, AiProviderClient providers) {
        this(legacy, providers, null, null, false, 0);
    }

    /** Legacy canary test constructor; nonzero user ID explicitly scopes enabled traffic. */
    public DefaultAiModelGateway(DeepSeekClient legacy, AiProviderClient providers,
                                 SpringAiDeepSeekAdapter springAi,
                                 boolean enabled, long canaryUser) {
        this(legacy, providers, springAi, null, enabled, canaryUser);
    }

    @Autowired
    public DefaultAiModelGateway(DeepSeekClient legacy, AiProviderClient providers,
                                 SpringAiDeepSeekAdapter springAi,
                                 SpringAiUniversalProviderAdapter universal,
                                 @Value("${matrix-prp.ai.spring-ai.enabled:true}") boolean enabled,
                                 @Value("${matrix-prp.ai.spring-ai.canary-user-id:0}") long canaryUser) {
        this.legacy = legacy;
        this.providers = providers;
        this.springAi = springAi;
        this.universal = universal;
        this.springAiEnabled = enabled;
        this.springAiCanaryUser = canaryUser;
    }

    @Override
    public String legacyModel() {
        return legacy.model();
    }

    @Override
    public void requireLegacyConfigured() {
        legacy.requireConfigured();
    }

    @Override
    public DeepSeekClient.Result stream(Target target, List<DeepSeekClient.ChatMessage> messages,
                                        int outputLimit, Consumer<String> delta) throws Exception {
        Objects.requireNonNull(target, "AI model target is required");
        boolean isLegacy = target.useLegacyDeepSeek();
        // Even server-configured DeepSeek requests use Spring AI when enabled.
        // The credential remains server-side and is never exposed to the browser.
        if (isLegacy) legacy.requireConfigured();
        AiSettingsService.Runtime config = isLegacy
            ? new AiSettingsService.Runtime(AiProviderCatalog.require("deepseek"),
                legacy.model(), legacy.serverApiKey(), true)
            : target.provider();

        // Default scope 0 means all authenticated users; a positive ID is a
        // deliberate rollback/canary override. Never try two transports in one call.
        if (springAiEnabled && (springAiCanaryUser <= 0 || CurrentUser.id() == springAiCanaryUser)) {
            if (config.provider().id().equals("deepseek")) {
                if (springAi == null) throw new IllegalStateException("Spring AI DeepSeek adapter unavailable");
                return springAi.stream(config, messages, outputLimit, delta);
            }
            if (universal == null) throw new IllegalStateException("Spring AI provider adapter unavailable");
            return universal.stream(config, messages, outputLimit, delta);
        }
        if (isLegacy) return legacy.stream(messages, outputLimit, delta);
        return providers.stream(config, messages, outputLimit, delta);
    }
}
