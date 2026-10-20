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
    private final boolean springAiEnabled;
    private final long springAiCanaryUser;

    /** Existing unit-test API. When only two dependencies are given, the canary is disabled. */
    public DefaultAiModelGateway(DeepSeekClient legacy, AiProviderClient providers) {
        this(legacy, providers, null, false, 0);
    }

    @Autowired
    public DefaultAiModelGateway(DeepSeekClient legacy, AiProviderClient providers,
                                 SpringAiDeepSeekAdapter springAi,
                                 @Value("${matrix-prp.ai.spring-ai.enabled:false}") boolean enabled,
                                 @Value("${matrix-prp.ai.spring-ai.canary-user-id:0}") long canaryUser) {
        this.legacy = legacy;
        this.providers = providers;
        this.springAi = springAi;
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
        if (target.useLegacyDeepSeek())
            return legacy.stream(messages, outputLimit, delta);
        AiSettingsService.Runtime config = target.provider();
        if (springAiEnabled && springAi != null && springAiCanaryUser > 0
                && config.provider().id().equals("deepseek") && !config.legacy()
                && CurrentUser.id() == springAiCanaryUser) {
            // No retries/failover, especially once a streamed delta was emitted.
            return springAi.stream(config, messages, outputLimit, delta);
        }
        return providers.stream(config, messages, outputLimit, delta);
    }
}
