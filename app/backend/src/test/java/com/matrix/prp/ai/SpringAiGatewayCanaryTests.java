package com.matrix.prp.ai;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import com.matrix.prp.auth.model.UserProfile;
import java.util.List;
import java.util.function.Consumer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

class SpringAiGatewayCanaryTests {
    private final DeepSeekClient legacy = mock(DeepSeekClient.class);
    private final AiProviderClient nativeClient = mock(AiProviderClient.class);
    private final SpringAiDeepSeekAdapter deepseek = mock(SpringAiDeepSeekAdapter.class);
    private final SpringAiUniversalProviderAdapter universal = mock(SpringAiUniversalProviderAdapter.class);
    private final List<DeepSeekClient.ChatMessage> prompt =
        List.of(new DeepSeekClient.ChatMessage("user","private message"));

    void login(long id) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(
                new UserProfile(id,"user"+id,"User"),null,List.of()));
    }
    @AfterEach void clear() { SecurityContextHolder.clearContext(); }

    AiSettingsService.Runtime runtime(String id,String model,String secret) {
        return new AiSettingsService.Runtime(AiProviderCatalog.require(id),model,secret,false);
    }

    @Test void emergencyKillSwitchRestoresExistingHttpRouteForEveryone() throws Exception {
        login(42);
        var disabled = new DefaultAiModelGateway(legacy,nativeClient,deepseek,universal,false,0);
        for (var provider : AiProviderCatalog.PROVIDERS) {
            var selected = runtime(provider.id(),provider.defaultModel(),"private-key");
            disabled.stream(AiModelGateway.Target.configured(selected),prompt,32,x->{});
            verify(nativeClient).stream(eq(selected),eq(prompt),eq(32),any());
        }
        when(legacy.model()).thenReturn("deepseek-chat");
        disabled.stream(AiModelGateway.Target.legacyDeepSeek(),prompt,32,x->{});
        verify(legacy).stream(eq(prompt),eq(32),any());
        verifyNoInteractions(deepseek,universal);
    }

    @Test void globalModeRoutesAllProviderChoicesAndUsersWithoutHttpFallback() throws Exception {
        var enabled = new DefaultAiModelGateway(legacy,nativeClient,deepseek,universal,true,0);
        var expected = new DeepSeekClient.Result("OK",2,1);
        Consumer<String> callback = x->{};
        login(7);
        for (var provider : AiProviderCatalog.PROVIDERS) {
            var selected = runtime(provider.id(),provider.defaultModel(),"per-user-key");
            if (provider.id().equals("deepseek"))
                when(deepseek.stream(selected,prompt,32,callback)).thenReturn(expected);
            else
                when(universal.stream(selected,prompt,32,callback)).thenReturn(expected);
            assertThat(enabled.stream(AiModelGateway.Target.configured(selected),prompt,32,callback))
                .isSameAs(expected);
            if (provider.id().equals("deepseek"))
                verify(deepseek).stream(selected,prompt,32,callback);
            else
                verify(universal).stream(selected,prompt,32,callback);
        }
        login(8);
        var another=runtime("qwen","qwen-max","another-user-key");
        when(universal.stream(another,prompt,32,callback)).thenReturn(expected);
        enabled.stream(AiModelGateway.Target.configured(another),prompt,32,callback);
        verify(universal).stream(another,prompt,32,callback);
        verifyNoInteractions(nativeClient);
    }

    @Test void serverKeyLegacyDeepSeekAlsoRoutesThroughSpringAiAndDoesNotExposeItsKey() throws Exception {
        login(42);
        when(legacy.model()).thenReturn("deepseek-chat");
        when(legacy.serverApiKey()).thenReturn("server-secret");
        var gateway = new DefaultAiModelGateway(legacy,nativeClient,deepseek,universal,true,0);
        var expected = new DeepSeekClient.Result("hello",0,0);
        when(deepseek.stream(any(),eq(prompt),eq(32),any())).thenReturn(expected);
        gateway.stream(AiModelGateway.Target.legacyDeepSeek(),prompt,32,s->{});
        var captor=org.mockito.ArgumentCaptor.forClass(AiSettingsService.Runtime.class);
        verify(deepseek).stream(captor.capture(),eq(prompt),eq(32),any());
        assertThat(captor.getValue().legacy()).isTrue();
        assertThat(captor.getValue().apiKey()).isEqualTo("server-secret");
        verify(legacy,never()).stream(anyList(),anyInt(),any());
    }

    @Test void optionalPositiveCanaryIdStillRestrictsEnabledTraffic() throws Exception {
        var gateway = new DefaultAiModelGateway(legacy,nativeClient,deepseek,universal,true,42);
        var user=runtime("qwen","qwen-plus","key");
        login(41);
        gateway.stream(AiModelGateway.Target.configured(user),prompt,16,s->{});
        verify(nativeClient).stream(eq(user),eq(prompt),eq(16),any());
        verifyNoInteractions(universal);
        login(42);
        gateway.stream(AiModelGateway.Target.configured(user),prompt,16,s->{});
        verify(universal).stream(eq(user),eq(prompt),eq(16),any());
    }

    @Test void failedStreamingNeverInvokesNativeAdapterOrRetries() throws Exception {
        login(42);
        var gateway = new DefaultAiModelGateway(legacy,nativeClient,deepseek,universal,true,0);
        var user=runtime("qwen","qwen-plus","private-key");
        Consumer<String> callback=x->{};
        when(universal.stream(user,prompt,16,callback)).thenAnswer(inv -> {
            callback.accept("partial");
            throw new IllegalStateException("upstream truncated");
        });
        assertThatThrownBy(() -> gateway.stream(
            AiModelGateway.Target.configured(user),prompt,16,callback))
            .isInstanceOf(IllegalStateException.class);
        verify(universal,times(1)).stream(user,prompt,16,callback);
        verifyNoInteractions(nativeClient);
    }
}
