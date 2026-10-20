package com.matrix.prp.ai;

import static org.assertj.core.api.Assertions.*;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;

/** Real Spring AI OpenAI-compatible request encoding via local providers, no paid calls. */
class SpringAiVisionModelClientTests {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final byte[] PNG = Base64.getDecoder().decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+pqX0AAAAASUVORK5CYII=");
    private static final String RESPONSE = """
        {"id":"vision-local","object":"chat.completion","created":1730000000,
         "model":"gpt-4.1-mini","choices":[{"index":0,
         "message":{"role":"assistant","content":"{\\"action\\":\\"meal.create\\"}"},
         "finish_reason":"stop"}],
         "usage":{"prompt_tokens":25,"completion_tokens":11,"total_tokens":36}}
        """;

    @Test void allowedProvidersSendActualInlineImageAndCorrectModel() throws Exception {
        for(String id:List.of("deepseek","openai","kimi","kimi-global"))
            simulate(id,200,false);
    }

    @Test void upstream429IsSanitizedAndNeverRetried() throws Exception {
        simulate("deepseek",429,false);
    }

    @Test void emptyVisionAnswerIsRejectedWithoutRetries() throws Exception {
        simulate("openai",200,true);
    }

    @Test void untrustedEndpointAndUnsupportedModelsFailBeforeSendingImages() {
        assertThatThrownBy(() -> new SpringAiVisionModelClient(
            Map.of("deepseek", URI.create("https://unexpected.example/chat/completions"))))
            .isInstanceOf(IllegalArgumentException.class);
        var client=new SpringAiVisionModelClient();
        var gemini=AiProviderCatalog.require("gemini");
        var config=new AiSettingsService.Runtime(gemini,gemini.defaultModel(),"test-secret",false);
        assertThatThrownBy(() -> client.complete(config,gemini.defaultModel(),
            "Return JSON","Look at the dish",PNG,"image/png"))
            .isInstanceOf(IllegalArgumentException.class);
        var deepseek=AiProviderCatalog.require("deepseek");
        var valid=new AiSettingsService.Runtime(deepseek,deepseek.defaultModel(),"test-secret",false);
        assertThatThrownBy(() -> client.complete(valid,"deepseek-flash",
            "Return JSON","Look at the dish",new byte[3_000_001],"image/png"))
            .isInstanceOf(ResponseStatusException.class).hasMessageContaining("400");
        assertThatThrownBy(() -> client.complete(valid,"deepseek-flash",
            "Return JSON","Look at the dish",PNG,"image/gif"))
            .isInstanceOf(ResponseStatusException.class).hasMessageContaining("400");
    }

    void simulate(String providerId,int status,boolean empty) throws Exception {
        var provider=AiProviderCatalog.require(providerId);
        String model=switch(providerId) {
            case "deepseek" -> "deepseek-flash";
            case "openai" -> "gpt-4.1-mini";
            default -> "kimi-k2.5";
        };
        AtomicInteger calls=new AtomicInteger();
        AtomicReference<JsonNode> sent=new AtomicReference<>();
        AtomicReference<String> auth=new AtomicReference<>();
        var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        URI endpoint=URI.create("http://127.0.0.1:"+server.getAddress().getPort()+
            provider.endpoint().getRawPath());
        server.createContext(endpoint.getPath(), exchange -> {
            try(exchange) {
                calls.incrementAndGet();
                auth.set(exchange.getRequestHeaders().getFirst("Authorization"));
                sent.set(JSON.readTree(exchange.getRequestBody().readAllBytes()));
                String response=status!=200 ? "{\\"private\\":\\"secret upstream payload\\"}" :
                    empty ? RESPONSE.replace("{\\\\\\"action\\\\\\":\\\\\\"meal.create\\\\\\"}", "") : RESPONSE;
                byte[] bytes=response.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set("Content-Type","application/json");
                exchange.sendResponseHeaders(status,bytes.length);
                exchange.getResponseBody().write(bytes);
            }
        });
        server.start();
        try {
            var client=new SpringAiVisionModelClient(Map.of(providerId,endpoint));
            var config=new AiSettingsService.Runtime(provider,provider.defaultModel(),
                "private-key-"+providerId,false);
            if(status==429) {
                assertThatThrownBy(() -> client.complete(config,model,
                    "Return JSON","This is a dish",PNG,"image/png"))
                    .isInstanceOf(ResponseStatusException.class)
                    .hasMessageContaining("429").hasNoCause()
                    .hasMessageNotContaining("secret upstream payload");
            } else if(empty) {
                assertThatThrownBy(() -> client.complete(config,model,
                    "Return JSON","This is a dish",PNG,"image/png"))
                    .isInstanceOf(ResponseStatusException.class)
                    .hasMessageContaining("Empty vision response");
            } else {
                var answer=client.complete(config,model,
                    "Return JSON","This is a dish",PNG,"image/png");
                assertThat(JSON.readTree(answer.answer()).path("action").asText())
                    .isEqualTo("meal.create");
                assertThat(answer.inputTokens()).isEqualTo(25);
                assertThat(answer.outputTokens()).isEqualTo(11);
            }
            assertThat(calls.get()).as(providerId).isEqualTo(1);
            JsonNode body=sent.get();
            assertThat(body.path("model").asText()).isEqualTo(model);
            assertThat(body.path("messages").path(0).path("role").asText()).isEqualTo("system");
            JsonNode user=body.path("messages").path(1);
            assertThat(user.path("role").asText()).isEqualTo("user");
            String dataUrl=user.path("content").path(1).path("image_url").path("url").asText();
            assertThat(dataUrl).startsWith("data:image/png;base64,");
            assertThat(Base64.getDecoder().decode(dataUrl.substring("data:image/png;base64,".length())))
                .containsExactly(PNG);
            assertThat(auth.get()).isEqualTo("Bearer private-key-"+providerId);
            assertThat(body.toString()).doesNotContain("private-key-"+providerId);
        } finally {server.stop(0);}
    }
}
