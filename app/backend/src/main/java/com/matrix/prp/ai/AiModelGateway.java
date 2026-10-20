package com.matrix.prp.ai;

import java.util.List;
import java.util.function.Consumer;

/**
 * Stable application-facing model boundary. Provider HTTP adapters remain behind this interface,
 * allowing a framework implementation to be introduced without changing conversation endpoints.
 */
public interface AiModelGateway {
    /**
     * A request selects exactly one transport. Legacy credentials are never put into a public DTO.
     * The legacy route exists only for backward compatibility with server-configured DeepSeek.
     */
    record Target(boolean useLegacyDeepSeek, AiSettingsService.Runtime provider) {
        public Target {
            if (useLegacyDeepSeek == (provider != null))
                throw new IllegalArgumentException("Exactly one AI model route is required");
        }
        public static Target legacyDeepSeek() { return new Target(true, null); }
        public static Target configured(AiSettingsService.Runtime provider) {
            return new Target(false, provider);
        }
    }

    String legacyModel();
    void requireLegacyConfigured();
    DeepSeekClient.Result stream(Target target, List<DeepSeekClient.ChatMessage> messages,
                                 int outputLimit, Consumer<String> delta) throws Exception;
}
