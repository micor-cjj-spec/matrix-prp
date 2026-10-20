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
    private final SpringAiDeepSeekAdapter experiment = mock(SpringAiDeepSeekAdapter.class);
    private final List<DeepSeekClient.ChatMessage> prompt =
        List.of(new DeepSeekClient.ChatMessage("user","confidential message"));

    void login(long userId) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(
                new UserProfile(userId,"user"+userId,"Canary"),null,List.of()));
    }
    @AfterEach void cleanup() { SecurityContextHolder.clearContext(); }

    private AiSettingsService.Runtime personal(String id,String model,String key) {
        return new AiSettingsService.Runtime(AiProviderCatalog.require(id),model,key,false);
    }

    @Test void defaultsRemainNativeEvenForIntendedOwner() throws Exception {
        login(42);
        var disabled = new DefaultAiModelGateway(legacy,nativeClient,experiment,false,42);
        var config = personal("deepseek","deepseek-chat","private-key-one");
        disabled.stream(AiModelGateway.Target.configured(config),prompt,128,x->{});
        verify(nativeClient).stream(eq(config),eq(prompt),eq(128),any());
        verifyNoInteractions(experiment);
    }

    @Test void canaryRequiresPositiveMatchingAuthenticatedUserAndPersonalDeepSeek() throws Exception {
        var enabled = new DefaultAiModelGateway(legacy,nativeClient,experiment,true,42);
        var canary = personal("deepseek","deepseek-chat","user-42-key");
        var ordinary = personal("qwen","qwen-plus","qwen-key");
        var serverKey = new AiSettingsService.Runtime(
            AiProviderCatalog.require("deepseek"),"deepseek-chat","server-key",true);
        Consumer<String> delta = ignored->{};
        login(41);
        enabled.stream(AiModelGateway.Target.configured(canary),prompt,16,delta);
        verify(nativeClient).stream(canary,prompt,16,delta);
        verifyNoInteractions(experiment);
        login(42);
        enabled.stream(AiModelGateway.Target.configured(ordinary),prompt,16,delta);
        enabled.stream(AiModelGateway.Target.configured(serverKey),prompt,16,delta);
        enabled.stream(AiModelGateway.Target.legacyDeepSeek(),prompt,16,delta);
        verify(nativeClient).stream(ordinary,prompt,16,delta);
        verify(nativeClient).stream(serverKey,prompt,16,delta);
        verify(legacy).stream(prompt,16,delta);
        verifyNoInteractions(experiment);
        var expected = new DeepSeekClient.Result("hello",0,0);
        when(experiment.stream(canary,prompt,16,delta)).thenReturn(expected);
        assertThat(enabled.stream(AiModelGateway.Target.configured(canary),prompt,16,delta))
            .isSameAs(expected);
        verify(experiment).stream(canary,prompt,16,delta);
        verify(nativeClient,times(1)).stream(canary,prompt,16,delta);
        // Canary user ID 0 cannot enable routing by itself.
        var unassigned = new DefaultAiModelGateway(legacy,nativeClient,experiment,true,0);
        unassigned.stream(AiModelGateway.Target.configured(canary),prompt,16,delta);
        verify(nativeClient,times(2)).stream(canary,prompt,16,delta);
    }

    @Test void differentCanaryUsersKeysNeverCrossAndStreamFailuresAreNotRetried() throws Exception {
        login(42);
        var gateway=new DefaultAiModelGateway(legacy,nativeClient,experiment,true,42);
        var owner=personal("deepseek","deepseek-chat","private-key-owner");
        var other=personal("deepseek","deepseek-chat","private-key-other");
        Consumer<String> callback = s->{};
        when(experiment.stream(owner,prompt,24,callback)).thenAnswer(call -> {
            callback.accept("part");
            throw new IllegalStateException("partial stream failed");
        });
        assertThatThrownBy(() -> gateway.stream(AiModelGateway.Target.configured(owner),
            prompt,24,callback)).isInstanceOf(IllegalStateException.class);
        verify(experiment,times(1)).stream(owner,prompt,24,callback);
        verifyNoInteractions(nativeClient);
        login(43);
        gateway.stream(AiModelGateway.Target.configured(other),prompt,24,callback);
        verify(nativeClient).stream(other,prompt,24,callback);
        verify(experiment,never()).stream(eq(other),anyList(),anyInt(),any());
    }
}
