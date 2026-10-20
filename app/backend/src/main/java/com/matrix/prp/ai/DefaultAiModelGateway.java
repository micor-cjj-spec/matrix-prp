package com.matrix.prp.ai;

import java.util.List;
import java.util.Objects;
import java.util.function.Consumer;
import org.springframework.stereotype.Component;

/** Compatibility adapter: preserves the pre-existing DeepSeek and provider stream parsers. */
@Component
public class DefaultAiModelGateway implements AiModelGateway {
    private final DeepSeekClient legacy;
    private final AiProviderClient providers;

    public DefaultAiModelGateway(DeepSeekClient legacy, AiProviderClient providers) {
        this.legacy = legacy;
        this.providers = providers;
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
        return providers.stream(target.provider(), messages, outputLimit, delta);
    }
}
