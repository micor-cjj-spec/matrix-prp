package com.matrix.prp.ai;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import com.matrix.prp.auth.model.UserProfile;
import java.util.List;
import java.util.function.Consumer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

class ObservedAiModelGatewayTests {
    private final DeepSeekClient deepSeek = mock(DeepSeekClient.class);
    private final AiProviderClient providers = mock(AiProviderClient.class);
    private final AiInvocationAudit audit = mock(AiInvocationAudit.class);
    private final ObservedAiModelGateway gateway =
        new ObservedAiModelGateway(new DefaultAiModelGateway(deepSeek,providers),audit);
    private final List<DeepSeekClient.ChatMessage> messages =
        List.of(new DeepSeekClient.ChatMessage("user","PRIVATE USER PROMPT"));
    @BeforeEach void login() {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(new UserProfile(42L,"sample","Sample"),null,List.of()));
        when(deepSeek.model()).thenReturn("deepseek-chat");
    }
    @AfterEach void clear() { SecurityContextHolder.clearContext(); }

    @Test void measuresFirstTokenAndPreservesStreamingPayload() throws Exception {
        StringBuilder deltas = new StringBuilder();
        when(deepSeek.stream(anyList(),eq(100),any())).thenAnswer(call -> {
            Consumer<String> consumer = call.getArgument(2);
            consumer.accept("hel"); consumer.accept("lo");
            return new DeepSeekClient.Result("hello",30,10);
        });
        var response=gateway.stream(AiModelGateway.Target.legacyDeepSeek(),
            messages,100,deltas::append);
        assertThat(response.answer()).isEqualTo("hello");
        assertThat(deltas.toString()).isEqualTo("hello");
        var captured=org.mockito.ArgumentCaptor.forClass(AiInvocationAudit.Entry.class);
        verify(audit).record(captured.capture());
        var row=captured.getValue();
        assertThat(row.userId()).isEqualTo(42);
        assertThat(row.provider()).isEqualTo("deepseek");
        assertThat(row.model()).isEqualTo("deepseek-chat");
        assertThat(row.status()).isEqualTo("SUCCESS");
        assertThat(row.credentialSource()).isEqualTo("SERVER");
        assertThat(row.firstTokenMs()).isNotNull().isGreaterThanOrEqualTo(0);
        assertThat(row.elapsedMs()).isGreaterThanOrEqualTo(row.firstTokenMs());
        assertThat(row.inputTokens()).isEqualTo(30);
        assertThat(row.outputTokens()).isEqualTo(10);
        verifyNoInteractions(providers);
    }

    @Test void mapsErrorsWithoutLoggingSecretsOrRetrying() throws Exception {
        var runtime=new AiSettingsService.Runtime(
            AiProviderCatalog.require("qwen"),"qwen-plus","private-key",false);
        when(providers.stream(eq(runtime),anyList(),eq(8),any()))
            .thenThrow(new ResponseStatusException(HttpStatus.TOO_MANY_REQUESTS,
                "user's confidential model prompt"));
        assertThatThrownBy(() -> gateway.stream(
            AiModelGateway.Target.configured(runtime),messages,8,x -> {}))
            .isInstanceOf(ResponseStatusException.class);
        var captured=org.mockito.ArgumentCaptor.forClass(AiInvocationAudit.Entry.class);
        verify(audit).record(captured.capture());
        var row=captured.getValue();
        assertThat(row.failureCategory()).isEqualTo("PROVIDER_RATE_LIMIT");
        assertThat(row.status()).isEqualTo("FAILURE");
        assertThat(row.inputTokens()).isNull();
        assertThat(row.firstTokenMs()).isNull();
        assertThat(row.toString()).doesNotContain("private-key","confidential","PRIVATE USER PROMPT");
        verify(providers,times(1)).stream(eq(runtime),anyList(),eq(8),any());
    }

    @Test void missingProviderUsageIsUnknownNotZero() throws Exception {
        when(deepSeek.stream(anyList(),eq(10),any()))
            .thenReturn(new DeepSeekClient.Result("answer",0,0));
        gateway.stream(AiModelGateway.Target.legacyDeepSeek(),messages,10,x->{});
        var captured=org.mockito.ArgumentCaptor.forClass(AiInvocationAudit.Entry.class);
        verify(audit).record(captured.capture());
        assertThat(captured.getValue().inputTokens()).isNull();
        assertThat(captured.getValue().outputTokens()).isNull();
        assertThat(captured.getValue().firstTokenMs()).isNull();
    }

    @Test void telemetryFailureDoesNotBreakModelStream() throws Exception {
        when(deepSeek.stream(anyList(),anyInt(),any()))
            .thenReturn(new DeepSeekClient.Result("OK",1,1));
        doThrow(new IllegalStateException("db unavailable")).when(audit).record(any());
        assertThat(gateway.stream(AiModelGateway.Target.legacyDeepSeek(),messages,8,x->{}).answer())
            .isEqualTo("OK");
    }

    @Test void tenantScopedQueriesAndUnknownUsageTotalsAreConsistent() {
        InMemoryAiInvocationAudit memory=new InMemoryAiInvocationAudit();
        var now=java.time.LocalDateTime.now(java.time.Clock.systemUTC());
        memory.record(new AiInvocationAudit.Entry(42L,"deepseek","deepseek-chat","SERVER",
            "SUCCESS",null,100L,50L,10L,2L,now));
        memory.record(new AiInvocationAudit.Entry(42L,"qwen","qwen-plus","PERSONAL",
            "FAILURE","TIMEOUT",200L,null,null,null,now));
        memory.record(new AiInvocationAudit.Entry(43L,"qwen","qwen-plus","PERSONAL",
            "SUCCESS",null,400L,100L,70L,70L,now));
        var summary=memory.summary(42L,7);
        assertThat(summary.totalRequests()).isEqualTo(2);
        assertThat(summary.successfulRequests()).isEqualTo(1);
        assertThat(summary.averageElapsedMs()).isEqualTo(150);
        assertThat(summary.averageFirstTokenMs()).isEqualTo(50);
        assertThat(summary.unreportedUsageRequests()).isEqualTo(1);
        assertThat(summary.inputTokens()).isEqualTo(10);
        assertThat(memory.recent(42L,7,10)).hasSize(2)
            .allSatisfy(record-> assertThat(record.model()).doesNotContain("PRIVATE"));
    }
}
