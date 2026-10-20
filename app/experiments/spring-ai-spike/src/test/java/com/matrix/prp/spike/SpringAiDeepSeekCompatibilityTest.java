package com.matrix.prp.spike;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.ai.deepseek.DeepSeekChatModel;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * Offline protocol tests against an in-process, OpenAI-compatible DeepSeek endpoint.
 * NO production credentials, internet AI requests, real costs or PRP business data.
 */
@SpringBootTest(
    classes = SpringAiDeepSeekCompatibilityTest.SpikeApplication.class,
    properties = {
        "spring.main.web-application-type=none",
        "spring.ai.model.chat=deepseek",
        "spring.ai.deepseek.api-key=offline-test-key",
        "spring.ai.deepseek.chat.options.model=deepseek-reasoner",
        "spring.ai.retry.max-attempts=1"
    })
class SpringAiDeepSeekCompatibilityTest {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final AtomicReference<JsonNode> LAST_REQUEST = new AtomicReference<>();
    private static final AtomicReference<String> LAST_AUTHORIZATION = new AtomicReference<>();
    private static final HttpServer SERVER = startFakeProvider();

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class SpikeApplication {}

    @DynamicPropertySource
    static void provider(DynamicPropertyRegistry props) {
        props.add("spring.ai.deepseek.base-url",
            () -> "http://127.0.0.1:" + SERVER.getAddress().getPort());
    }

    private static HttpServer startFakeProvider() {
        try {
            HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/chat/completions", SpringAiDeepSeekCompatibilityTest::respond);
            server.start();
            return server;
        } catch (IOException ex) {
            throw new IllegalStateException("Cannot start local DeepSeek fixture", ex);
        }
    }

    private static void respond(HttpExchange exchange) throws IOException {
        try (exchange) {
            LAST_AUTHORIZATION.set(exchange.getRequestHeaders().getFirst("Authorization"));
            JsonNode request = JSON.readTree(exchange.getRequestBody().readAllBytes());
            LAST_REQUEST.set(request);
            String body;
            if (request.path("stream").asBoolean(false)) {
                body = """
                    data: {"id":"chatcmpl-offline","object":"chat.completion.chunk","created":1730000000,"model":"deepseek-reasoner","choices":[{"index":0,"delta":{"role":"assistant","content":"hel"},"finish_reason":null}]}

                    data: {"id":"chatcmpl-offline","object":"chat.completion.chunk","created":1730000000,"model":"deepseek-reasoner","choices":[{"index":0,"delta":{"content":"lo"},"finish_reason":null}]}

                    data: {"id":"chatcmpl-offline","object":"chat.completion.chunk","created":1730000000,"model":"deepseek-reasoner","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

                    data: [DONE]

                    """;
                exchange.getResponseHeaders().set("Content-Type", "text/event-stream");
            } else {
                body = """
                    {"id":"chatcmpl-offline","object":"chat.completion","created":1730000000,
                     "model":"deepseek-reasoner","choices":[{"index":0,"message":{"role":"assistant",
                     "content":"pong"},"finish_reason":"stop"}],
                     "usage":{"prompt_tokens":6,"completion_tokens":2,"total_tokens":8}}
                    """;
                exchange.getResponseHeaders().set("Content-Type", "application/json");
            }
            byte[] data = body.getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, data.length);
            exchange.getResponseBody().write(data);
        }
    }

    @Autowired DeepSeekChatModel model;

    @AfterAll static void stopProvider() {
        SERVER.stop(0);
    }

    @Test void regularChatUsesConfiguredModelAndFakeProvider() {
        var response = model.call(new Prompt(new UserMessage("ping")));
        assertThat(response.getResult().getOutput().getText()).isEqualTo("pong");
        assertThat(LAST_AUTHORIZATION.get()).isEqualTo("Bearer offline-test-key");
        assertThat(LAST_REQUEST.get().path("model").asText()).isEqualTo("deepseek-reasoner");
        assertThat(LAST_REQUEST.get().path("stream").asBoolean()).isFalse();
    }

    @Test void streamingChatProducesAssistantDeltas() {
        List<String> deltas = model.stream(new Prompt(new UserMessage("hello")))
            .filter(r -> r.getResult() != null
                && r.getResult().getOutput() != null
                && r.getResult().getOutput().getText() != null
                && !r.getResult().getOutput().getText().isEmpty())
            .map(r -> r.getResult().getOutput().getText())
            .collectList().block(Duration.ofSeconds(15));
        assertThat(deltas).isNotEmpty();
        assertThat(String.join("", deltas)).isEqualTo("hello");
        assertThat(LAST_REQUEST.get().path("stream").asBoolean()).isTrue();
    }
}
