package com.matrix.prp.ai;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import java.util.List;
import java.util.function.Consumer;
import org.junit.jupiter.api.Test;

class AiModelGatewayTests {
    private final DeepSeekClient legacy = mock(DeepSeekClient.class);
    private final AiProviderClient providers = mock(AiProviderClient.class);
    private final AiModelGateway gateway = new DefaultAiModelGateway(legacy, providers);
    private final List<DeepSeekClient.ChatMessage> messages =
        List.of(new DeepSeekClient.ChatMessage("user", "hello"));

    @Test
    void legacyChatPreservesDeepSeekClientAndDeltaCallback() throws Exception {
        StringBuilder streamed = new StringBuilder();
        Consumer<String> delta = streamed::append;
        DeepSeekClient.Result expected = new DeepSeekClient.Result("hello", 7, 2);
        when(legacy.stream(messages, 128, delta)).thenAnswer(call -> {
            delta.accept("hello");
            return expected;
        });

        assertThat(gateway.stream(AiModelGateway.Target.legacyDeepSeek(), messages, 128, delta))
            .isEqualTo(expected);
        assertThat(streamed.toString()).isEqualTo("hello");
        verifyNoInteractions(providers);
    }

    @Test
    void configuredModelAlwaysUsesProviderAdapterEvenForLegacyCredentials() throws Exception {
        var runtime = new AiSettingsService.Runtime(
            AiProviderCatalog.require("deepseek"), "deepseek-chat", "server-key", true);
        DeepSeekClient.Result expected = new DeepSeekClient.Result("OK", 2, 1);
        Consumer<String> delta = part -> {};
        when(providers.stream(runtime, messages, 16, delta)).thenReturn(expected);

        assertThat(gateway.stream(AiModelGateway.Target.configured(runtime),
            messages, 16, delta)).isEqualTo(expected);
        verifyNoInteractions(legacy);
    }

    @Test
    void badTargetsFailClosedWithoutDispatchingProvider() {
        var runtime = new AiSettingsService.Runtime(
            AiProviderCatalog.require("claude"), "claude-sonnet-4-5", "secret", false);
        assertThatThrownBy(() -> new AiModelGateway.Target(false, null))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new AiModelGateway.Target(true, runtime))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> gateway.stream(null, messages, 16, part -> {}))
            .isInstanceOf(NullPointerException.class);
        verifyNoInteractions(providers, legacy);
    }

    @Test
    void providerFailuresAreNotSilentlyReplayedOrDowngraded() throws Exception {
        var runtime = new AiSettingsService.Runtime(
            AiProviderCatalog.require("qwen"), "qwen-plus", "secret", false);
        Consumer<String> delta = part -> {};
        when(providers.stream(runtime, messages, 16, delta))
            .thenThrow(new IllegalStateException("upstream failed"));

        assertThatThrownBy(() -> gateway.stream(AiModelGateway.Target.configured(runtime),
            messages, 16, delta))
            .isInstanceOf(IllegalStateException.class).hasMessageContaining("upstream failed");
        verify(providers, times(1)).stream(runtime, messages, 16, delta);
        verifyNoInteractions(legacy);
    }
}
