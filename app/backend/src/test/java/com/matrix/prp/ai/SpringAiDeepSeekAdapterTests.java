package com.matrix.prp.ai;

import static org.assertj.core.api.Assertions.*;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

class SpringAiDeepSeekAdapterTests {
    private static final ObjectMapper JSON = new ObjectMapper();

    private static AiSettingsService.Runtime target(String secret) {
        return new AiSettingsService.Runtime(
            AiProviderCatalog.require("deepseek"),"deepseek-chat",secret,false);
    }

    @Test void worksWithRealSpringAiStreamAndPerRequestPersonalKeys() throws Exception {
        var auth = new AtomicReference<String>();
        var body = new AtomicReference<JsonNode>();
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        server.createContext("/chat/completions", exchange -> {
            try (exchange) {
                auth.set(exchange.getRequestHeaders().getFirst("Authorization"));
                body.set(JSON.readTree(exchange.getRequestBody().readAllBytes()));
                String response = """
                    data: {"id":"chatcmpl-1","object":"chat.completion.chunk","created":1730000000,"model":"deepseek-chat","choices":[{"index":0,"delta":{"role":"assistant","content":"hel"},"finish_reason":null}]}

                    data: {"id":"chatcmpl-1","object":"chat.completion.chunk","created":1730000000,"model":"deepseek-chat","choices":[{"index":0,"delta":{"content":"lo"},"finish_reason":null}]}

                    data: {"id":"chatcmpl-1","object":"chat.completion.chunk","created":1730000000,"model":"deepseek-chat","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

                    data: [DONE]

                    """;
                byte[] bytes = response.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().add("Content-Type","text/event-stream");
                exchange.sendResponseHeaders(200,bytes.length);
                exchange.getResponseBody().write(bytes);
            }
        });
        server.start();
        try {
            var adapter=new SpringAiDeepSeekAdapter("http://127.0.0.1:"+server.getAddress().getPort());
            var messages=List.of(new DeepSeekClient.ChatMessage("system","Only test."),
                new DeepSeekClient.ChatMessage("user","hello"));
            var output=new StringBuilder();
            var result=adapter.stream(target("personal-key-A"),messages,64,output::append);
            assertThat(result.answer()).isEqualTo("hello");
            assertThat(output.toString()).isEqualTo("hello");
            assertThat(auth.get()).isEqualTo("Bearer personal-key-A");
            assertThat(body.get().path("model").asText()).isEqualTo("deepseek-chat");
            assertThat(body.get().path("max_tokens").asInt()).isEqualTo(64);
            assertThat(body.get().path("messages").toString()).contains("Only test.","hello");
            output.setLength(0);
            adapter.stream(target("personal-key-B"),messages,64,output::append);
            assertThat(auth.get()).isEqualTo("Bearer personal-key-B");
            assertThat(output.toString()).isEqualTo("hello");
        } finally {
            server.stop(0);
        }
    }

    @Test void refusesUnsupportedProviderOrInvalidInputsBeforeAnyNetworkCall() {
        var adapter=new SpringAiDeepSeekAdapter();
        var other=new AiSettingsService.Runtime(
            AiProviderCatalog.require("qwen"),"qwen-plus","qwen-key",false);
        var empty=List.of(new DeepSeekClient.ChatMessage("user","hi"));
        assertThatThrownBy(()->adapter.stream(other,empty,16,x->{}))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(()->adapter.stream(target("x"),empty,0,x->{}))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(()->adapter.stream(target("x"),
            List.of(new DeepSeekClient.ChatMessage("tool","untrusted")),16,x->{}))
            .isInstanceOf(IllegalArgumentException.class);
    }

    @Test void upstreamErrorsRetainPRPRateLimitAndAvailabilitySemanticsWithoutReplay() throws Exception {
        for (int code : new int[]{429,503,401}) {
            var calls = new java.util.concurrent.atomic.AtomicInteger();
            var server = HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
            server.createContext("/chat/completions", exchange -> {
                try (exchange) {
                    calls.incrementAndGet();
                    byte[] body = "secret-upstream-error-body".getBytes(StandardCharsets.UTF_8);
                    exchange.getResponseHeaders().add("Content-Type","application/json");
                    exchange.sendResponseHeaders(code,body.length);
                    exchange.getResponseBody().write(body);
                }
            });
            server.start();
            try {
                var adapter = new SpringAiDeepSeekAdapter(
                    "http://127.0.0.1:" + server.getAddress().getPort());
                var input = List.of(new DeepSeekClient.ChatMessage("user","PRIVATE PROMPT"));
                var exception = catchThrowable(() -> adapter.stream(
                    target("private-key-for-test"), input, 16, ignored -> {}));
                assertThat(exception)
                    .isInstanceOf(org.springframework.web.server.ResponseStatusException.class);
                var translated = (org.springframework.web.server.ResponseStatusException) exception;
                assertThat(translated.getStatusCode().value())
                    .isEqualTo(code == 429 ? 429 : code == 503 ? 503 : 502);
                assertThat(translated.toString()).doesNotContain(
                    "secret-upstream-error-body","private-key-for-test","PRIVATE PROMPT");
                assertThat(calls.get()).isEqualTo(1);
            } finally {
                server.stop(0);
            }
        }
    }
}
