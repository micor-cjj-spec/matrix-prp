package com.matrix.prp.ai;

import static org.assertj.core.api.Assertions.*;

import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

/**
 * Exercises real Spring AI 1.1 WebClient decoding with one loopback model request.
 * A model finish_reason is deliberately present in the truncated success fixture.
 */
class SpringAiStreamTerminationTests {
    private static final String CHUNKS = """
        data: {"id":"test-stream","object":"chat.completion.chunk","created":1730000000,"model":"deepseek-chat","choices":[{"index":0,"delta":{"role":"assistant","content":"hello"},"finish_reason":null}]}

        data: {"id":"test-stream","object":"chat.completion.chunk","created":1730000000,"model":"deepseek-chat","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

        """;

    private static AiSettingsService.Runtime runtime() {
        return new AiSettingsService.Runtime(AiProviderCatalog.require("deepseek"),
            "deepseek-chat", "test-personal-api-key", false);
    }

    @Test void onlyRealTerminationSentinelAllowsModelSuccess() throws Exception {
        check(CHUNKS + "data: [DONE]\n\n",true,false);
    }

    @Test void eofAfterFinishReasonButBeforeDoneMustFail() throws Exception {
        check(CHUNKS,false,false);
    }

    @Test void eofWithoutFinishReasonMustFail() throws Exception {
        check(CHUNKS.substring(0,CHUNKS.indexOf("data: {",10)),false,false);
    }

    @Test void aSpuriousMarkerInsideJsonDoesNotCompleteTheStream() throws Exception {
        String jsonMarker = CHUNKS.replace("hello","data: [DONE]");
        check(jsonMarker,false,false);
    }

    @Test void callbackExceptionDoesNotTriggerReplay() throws Exception {
        check(CHUNKS + "data: [DONE]\n\n",false,true);
    }

    @Test void upstreamDoneWithNoAnswerFails() throws Exception {
        check("data: [DONE]\n\n",false,false);
    }

    private void check(String events, boolean expectedSuccess, boolean failCallback) throws Exception {
        AtomicInteger calls = new AtomicInteger();
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        server.createContext("/chat/completions",exchange -> {
            try(exchange) {
                calls.incrementAndGet();
                exchange.getRequestBody().readAllBytes();
                byte[] bytes = events.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set("Content-Type","text/event-stream");
                exchange.sendResponseHeaders(200,bytes.length);
                exchange.getResponseBody().write(bytes);
            }
        });
        server.start();
        try {
            var adapter = new SpringAiDeepSeekAdapter("http://127.0.0.1:" + server.getAddress().getPort());
            var messages = List.of(new DeepSeekClient.ChatMessage("user","private prompt"));
            StringBuilder out = new StringBuilder();
            org.assertj.core.api.ThrowableAssert.ThrowingCallable invoke = () -> {
                var result = adapter.stream(runtime(),messages,32,part -> {
                    if (failCallback) throw new IllegalStateException("frontend disconnected");
                    out.append(part);
                });
                assertThat(result.answer()).isEqualTo("hello");
            };
            if (expectedSuccess) {
                assertThatCode(invoke).doesNotThrowAnyException();
                assertThat(out.toString()).isEqualTo("hello");
            } else if (failCallback) {
                assertThatThrownBy(invoke).hasMessageContaining("frontend disconnected");
            } else {
                assertThatThrownBy(invoke).isInstanceOf(IllegalStateException.class)
                    .hasMessageContaining(events.startsWith("data: [DONE]") ?
                        "empty response" : "completion sentinel");
            }
            assertThat(calls.get()).isEqualTo(1);
        } finally {
            server.stop(0);
        }
    }
}
