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
import org.springframework.web.server.ResponseStatusException;

class SpringAiStructuredModelClientTests {
    private static final ObjectMapper JSON=new ObjectMapper();
    private static final String OPENAI_RESPONSE = """
        {"id":"cmpl-offline","object":"chat.completion","created":1730000000,
         "model":"gpt-4.1-mini","choices":[{"index":0,
         "message":{"role":"assistant","content":"{\\"action\\":\\"meal.create\\"}"},
         "finish_reason":"stop"}],
         "usage":{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15}}
        """;
    private static final String ANTHROPIC_RESPONSE = """
        {"id":"msg_offline","type":"message","role":"assistant",
         "model":"claude-sonnet-4-5","content":[{"type":"text","text":"{\\"action\\":\\"meal.create\\"}"}],
         "stop_reason":"end_turn","stop_sequence":null,
         "usage":{"input_tokens":10,"output_tokens":5}}
        """;

    @Test void allSevenProvidersCompleteStructuredTextWithoutLeaksOrRetries() throws Exception {
        for(var provider:AiProviderCatalog.PROVIDERS) simulate(provider,200,false);
    }

    @Test void malformedEmptyAnswerIsRejectedWithoutSecondRequest() throws Exception {
        simulate(AiProviderCatalog.require("deepseek"),200,true);
    }

    @Test void provider429PropagatesQuotaSourceWithoutBody() throws Exception {
        simulate(AiProviderCatalog.require("qwen"),429,false);
        simulate(AiProviderCatalog.require("claude"),429,false);
    }

    @Test void practiceJsonModeSendsProviderResponseFormat() throws Exception {
        simulate(AiProviderCatalog.require("deepseek"),200,false,true,"Generate JSON questions");
    }

    @Test void acceptsMaximumValidPracticeExplanationPrompt() throws Exception {
        simulate(AiProviderCatalog.require("deepseek"),200,false,false,"x".repeat(35_000));
    }

    @Test void rejectsOversizedPromptBeforeNetworkAccess() {
        var client=new SpringAiStructuredModelClient();
        var provider=AiProviderCatalog.require("deepseek");
        var config=new AiSettingsService.Runtime(provider,provider.defaultModel(),"test-key",true);
        assertThatThrownBy(()->client.complete(config,List.of(
            new DeepSeekClient.ChatMessage("user","x".repeat(SpringAiStructuredModelClient.MAX_MESSAGE_CHARS+1))),100))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("limit");
    }

    void simulate(AiProviderCatalog.Provider provider,int code,boolean empty) throws Exception {
        simulate(provider,code,empty,false,"Lunch calories");
    }

    void simulate(AiProviderCatalog.Provider provider,int code,boolean empty,
                  boolean jsonObject,String userText) throws Exception {
        AtomicInteger calls=new AtomicInteger();
        AtomicReference<JsonNode> sent=new AtomicReference<>();
        AtomicReference<String> key=new AtomicReference<>();
        var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        URI endpoint=URI.create("http://127.0.0.1:"+server.getAddress().getPort()
            +provider.endpoint().getRawPath());
        server.createContext(endpoint.getPath(),exchange->{
            try(exchange){
                calls.incrementAndGet();
                key.set(exchange.getRequestHeaders().getFirst(
                    provider.anthropic()?"x-api-key":"Authorization"));
                sent.set(JSON.readTree(exchange.getRequestBody().readAllBytes()));
                String response=code!=200?"{\"error\":\"private upstream response\"}":
                    provider.anthropic()?ANTHROPIC_RESPONSE:
                    empty?OPENAI_RESPONSE.replace("{\\\"action\\\":\\\"meal.create\\\"}",""):
                          OPENAI_RESPONSE;
                byte[] bytes=response.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set("Content-Type","application/json");
                exchange.sendResponseHeaders(code,bytes.length);
                exchange.getResponseBody().write(bytes);
            }
        });
        server.start();
        try {
            var client=new SpringAiStructuredModelClient(Map.of(provider.id(),endpoint));
            var config=new AiSettingsService.Runtime(provider,provider.defaultModel(),
                "test-secret-"+provider.id(),false);
            var prompt=List.of(new DeepSeekClient.ChatMessage("system","Return JSON"),
                new DeepSeekClient.ChatMessage("user",userText));
            if(code==429){
                assertThatThrownBy(()->client.complete(config,prompt,2500,jsonObject))
                    .isInstanceOf(ResponseStatusException.class)
                    .hasMessageContaining("429")
                    .hasNoCause()
                    .hasMessageNotContaining("private upstream response");
            }else if(empty){
                assertThatThrownBy(()->client.complete(config,prompt,2500))
                    .isInstanceOf(ResponseStatusException.class)
                    .hasMessageContaining("empty response");
            } else {
                var result=client.complete(config,prompt,2500,jsonObject);
                assertThat(JSON.readTree(result.answer()).path("action").asText())
                    .isEqualTo("meal.create");
                assertThat(result.inputTokens()).isEqualTo(10);
                assertThat(result.outputTokens()).isEqualTo(5);
            }
            assertThat(calls.get()).as(provider.id()).isEqualTo(1);
            assertThat(sent.get().path("model").asText()).isEqualTo(provider.defaultModel());
            if (provider.id().equals("deepseek")) {
                assertThat(sent.get().path("response_format").path("type").asText())
                    .isEqualTo(jsonObject ? "json_object" : "");
            }
            assertThat(key.get()).isEqualTo(provider.anthropic()
                ?"test-secret-"+provider.id():"Bearer test-secret-"+provider.id());
            assertThat(sent.get().toString()).doesNotContain("test-secret-"+provider.id());
        }finally{server.stop(0);}
    }

    @Test void rejectsUntrustedDestinationsAndWrongModelWithoutNetwork() {
        assertThatThrownBy(()->new SpringAiStructuredModelClient(
            Map.of("openai",URI.create("https://untrusted.example/v1/chat/completions"))))
            .isInstanceOf(IllegalArgumentException.class);
        var client=new SpringAiStructuredModelClient();
        var wrong=new AiSettingsService.Runtime(AiProviderCatalog.require("deepseek"),
            "unapproved-model","test-key",true);
        assertThatThrownBy(()->client.complete(wrong,List.of(
            new DeepSeekClient.ChatMessage("user","test")),100))
            .isInstanceOf(IllegalArgumentException.class);
    }
}
