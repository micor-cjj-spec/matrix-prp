package com.matrix.prp.ai;

import static org.assertj.core.api.Assertions.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

class SpringAiUniversalProviderAdapterTests {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final String OPENAI_EVENTS = """
        data: {"id":"chatcmpl-1","object":"chat.completion.chunk","created":1730000000,"model":"qwen-plus","choices":[{"index":0,"delta":{"role":"assistant","content":"hel"},"finish_reason":null}]}

        data: {"id":"chatcmpl-1","object":"chat.completion.chunk","created":1730000000,"model":"qwen-plus","choices":[{"index":0,"delta":{"content":"lo"},"finish_reason":null}]}

        data: {"id":"chatcmpl-1","object":"chat.completion.chunk","created":1730000000,"model":"qwen-plus","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

        """;
    private static final String ANTHROPIC_EVENTS = """
        event: message_start
        data: {"type":"message_start","message":{"id":"msg_test","type":"message","role":"assistant","content":[],"model":"claude-sonnet-4-5","stop_reason":null,"stop_sequence":null,"usage":{"input_tokens":4,"output_tokens":0}}}

        event: content_block_start
        data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}

        event: content_block_delta
        data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"hello"}}

        event: content_block_stop
        data: {"type":"content_block_stop","index":0}

        event: message_delta
        data: {"type":"message_delta","delta":{"stop_reason":"end_turn","stop_sequence":null},"usage":{"output_tokens":2}}

        """;

    @Test void allSixNonDeepSeekProvidersUseOneSpringAiRequestAndOwnCredentials() throws Exception {
        for (var provider : AiProviderCatalog.PROVIDERS) {
            if ("deepseek".equals(provider.id())) continue;
            mockCall(provider, true, 200, false);
        }
    }

    @Test void terminatedWithoutProviderSentinelFailsForOpenAiAndClaude() throws Exception {
        mockCall(AiProviderCatalog.require("qwen"), false, 200, false);
        mockCall(AiProviderCatalog.require("claude"), false, 200, false);
    }

    @Test void provider429PreservesQuotaSourceWithoutReplay() throws Exception {
        mockCall(AiProviderCatalog.require("kimi"), false, 429, false);
        mockCall(AiProviderCatalog.require("claude"), false, 429, false);
    }

    @Test void callbackFailureNeverRetriesOrFallsBack() throws Exception {
        mockCall(AiProviderCatalog.require("openai"), true, 200, true);
    }

    private void mockCall(AiProviderCatalog.Provider provider, boolean terminal, int status,
                          boolean throwCallback) throws Exception {
        AtomicInteger calls = new AtomicInteger();
        AtomicReference<String> auth = new AtomicReference<>();
        AtomicReference<String> authorization = new AtomicReference<>();
        AtomicReference<JsonNode> request = new AtomicReference<>();
        var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        URI destination=URI.create("http://127.0.0.1:" + server.getAddress().getPort()
            + provider.endpoint().getRawPath());
        server.createContext(destination.getPath(), exchange -> {
            try (exchange) {
                calls.incrementAndGet();
                auth.set(exchange.getRequestHeaders().getFirst("x-api-key"));
                authorization.set(exchange.getRequestHeaders().getFirst("Authorization"));
                request.set(JSON.readTree(exchange.getRequestBody().readAllBytes()));
                String body = status == 200
                    ? (provider.anthropic() ? ANTHROPIC_EVENTS + (terminal
                        ? "event: message_stop\ndata: {\"type\":\"message_stop\"}\n\n" : "")
                        : OPENAI_EVENTS + (terminal ? "data: [DONE]\n\n" : ""))
                    : "{\"error\":\"private upstream error\"}";
                byte[] data=body.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set("Content-Type",status==200
                    ? "text/event-stream" : "application/json");
                exchange.sendResponseHeaders(status,data.length);
                exchange.getResponseBody().write(data);
            }
        });
        server.start();
        try {
            var adapter=new SpringAiUniversalProviderAdapter(Map.of(provider.id(),destination));
            var selection=new AiSettingsService.Runtime(provider,provider.defaultModel(),
                "secret-for-" + provider.id(),false);
            var deltas=new StringBuilder();
            var messages=List.of(new DeepSeekClient.ChatMessage("system","Only answer in brief"),
                new DeepSeekClient.ChatMessage("user","ping"));
            org.assertj.core.api.ThrowableAssert.ThrowingCallable call=()->{
                var result=adapter.stream(selection,messages,64,part -> {
                    if(throwCallback)throw new IllegalStateException("callback disconnected");
                    deltas.append(part);
                });
                assertThat(result.answer()).isEqualTo("hello");
            };
            if(status==429) {
                assertThatThrownBy(call)
                    .isInstanceOf(org.springframework.web.server.ResponseStatusException.class)
                    .hasMessageContaining("429");
            } else if(throwCallback) {
                assertThatThrownBy(call).hasMessageContaining("callback disconnected");
            } else if(!terminal) {
                assertThatThrownBy(call).isInstanceOf(IllegalStateException.class)
                    .hasMessageContaining("completion sentinel");
            } else {
                assertThatCode(call).doesNotThrowAnyException();
                assertThat(deltas.toString()).isEqualTo("hello");
            }
            assertThat(calls.get()).as(provider.id()).isEqualTo(1);
            assertThat(request.get().path("model").asText()).isEqualTo(provider.defaultModel());
            if(provider.anthropic()) {
                assertThat(auth.get()).isEqualTo("secret-for-"+provider.id());
            } else {
                assertThat(authorization.get()).isEqualTo("Bearer secret-for-"+provider.id());
            }
        } finally { server.stop(0); }
    }

    @Test void onlyPreapprovedLoopbackTestEndpointMayOverrideProviderDestinations() {
        assertThatThrownBy(()->new SpringAiUniversalProviderAdapter(Map.of(
            "openai",URI.create("https://example.com/v1/chat/completions"))))
            .isInstanceOf(IllegalArgumentException.class);
    }
}
