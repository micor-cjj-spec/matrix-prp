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
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.ai.chat.messages.AssistantMessage;

class SpringAiToolPlannerTests {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final AiToolRegistry.Definition NAVIGATION =
        new AiToolRegistry.Definition("navigation_open","","Read-only PRP navigation",
            Map.of("type","object","properties",Map.of("module",
                Map.of("type","string")),"additionalProperties",false));
    private static final AiToolRegistry.Definition FINANCE =
        new AiToolRegistry.Definition("finance_monthly","finance","Read current user monthly finance",
            Map.of("type","object","properties",Map.of("month",
                Map.of("type","string")),"additionalProperties",false));
    private static final String OPENAI_TOOL_RESPONSE = """
        {"id":"chatcmpl-offline","object":"chat.completion","created":1730000000,
         "model":"gpt-4.1-mini","choices":[{"index":0,
         "message":{"role":"assistant","content":null,"tool_calls":[{
            "id":"call_01","type":"function","function":{"name":"navigation_open",
            "arguments":"{\\"module\\":\\"tasks\\"}"}}]},
          "finish_reason":"tool_calls"}],
         "usage":{"prompt_tokens":20,"completion_tokens":5,"total_tokens":25}}
        """;
    private static final String ANTHROPIC_TOOL_RESPONSE = """
        {"id":"msg_offline","type":"message","role":"assistant","model":"claude-sonnet-4-5",
         "content":[{"type":"tool_use","id":"toolu_01","name":"navigation_open",
          "input":{"module":"tasks"}}],"stop_reason":"tool_use","stop_sequence":null,
         "usage":{"input_tokens":20,"output_tokens":5}}
        """;

    @Test void allProvidersProposeFunctionsWithoutExecutingAnyCallback() throws Exception {
        for (var provider : AiProviderCatalog.PROVIDERS) simulate(provider,200,true);
    }

    @Test void rejectsUpstreamRateLimitWithoutRepeatingProviderRequest() throws Exception {
        simulate(AiProviderCatalog.require("openai"),429,false);
    }

    void simulate(AiProviderCatalog.Provider provider,int status,boolean success) throws Exception {
        var calls=new AtomicInteger();
        var request=new AtomicReference<JsonNode>();
        var key=new AtomicReference<String>();
        var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        URI endpoint=URI.create("http://127.0.0.1:"+server.getAddress().getPort()
            + provider.endpoint().getRawPath());
        server.createContext(endpoint.getPath(), exchange -> {
            try(exchange) {
                calls.incrementAndGet();
                key.set(exchange.getRequestHeaders().getFirst(provider.anthropic()
                    ? "x-api-key":"Authorization"));
                request.set(JSON.readTree(exchange.getRequestBody().readAllBytes()));
                String response=status==200
                    ? provider.anthropic()?ANTHROPIC_TOOL_RESPONSE:OPENAI_TOOL_RESPONSE
                    : "{\"error\":\"do not print provider internals\"}";
                byte[] bytes=response.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set("Content-Type","application/json");
                exchange.sendResponseHeaders(status,bytes.length);
                exchange.getResponseBody().write(bytes);
            }
        });
        server.start();
        try {
            var planner=new SpringAiToolPlanner(JSON,Map.of(provider.id(),endpoint));
            var config=new AiSettingsService.Runtime(provider,provider.defaultModel(),
                "private-"+provider.id(),false);
            var messages=List.of(new DeepSeekClient.ChatMessage("system","Only read"),
                new DeepSeekClient.ChatMessage("user","Open my tasks"));
            if(success) {
                var callsFromModel=planner.plan(config,messages,List.of(NAVIGATION));
                assertThat(callsFromModel).as(provider.id()).hasSize(1);
                assertThat(callsFromModel.getFirst().name()).isEqualTo("navigation_open");
                assertThat(callsFromModel.getFirst().arguments().path("module").asText()).isEqualTo("tasks");
                assertThat(request.get().path("tools")).isNotEmpty();
                // A schema-only ToolCallback would throw if Spring AI executed it.
            } else {
                assertThatThrownBy(()->planner.plan(config,messages,List.of(NAVIGATION)))
                    .isInstanceOf(org.springframework.web.server.ResponseStatusException.class)
                    .hasMessageContaining("429")
                    .hasNoCause();
            }
            assertThat(calls.get()).as(provider.id()).isEqualTo(1);
            assertThat(key.get()).isEqualTo(provider.anthropic()
                ? "private-"+provider.id() : "Bearer private-"+provider.id());
            assertThat(request.get().path("model").asText()).isEqualTo(provider.defaultModel());
            assertThat(request.get().toString()).doesNotContain("private-"+provider.id());
        } finally { server.stop(0); }
    }

    @Test void rejectsUnapprovedAndMalformedToolProposalsBeforePRPExecution() throws Exception {
        var planner=new SpringAiToolPlanner(JSON);
        var ok=new AssistantMessage.ToolCall("call_1","function","navigation_open","{\"module\":\"tasks\"}");
        assertThat(planner.validateProposals(List.of(ok),Set.of("navigation_open"))).hasSize(1);
        assertThatThrownBy(()->planner.validateProposals(List.of(ok),Set.of("finance_monthly")))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(()->planner.validateProposals(
            List.of(new AssistantMessage.ToolCall("1","function","finance_monthly","{}")),
            Set.of("navigation_open"))).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(()->planner.validateProposals(
            List.of(new AssistantMessage.ToolCall("1","function","navigation_open","[]")),
            Set.of("navigation_open"))).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(()->planner.validateProposals(
            List.of(new AssistantMessage.ToolCall("1","function","navigation_open","{\"data\":\""
                +"A".repeat(2200)+"\"}")),Set.of("navigation_open")))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(()->planner.validateProposals(
            List.of(ok,ok,ok,ok,ok),Set.of("navigation_open")))
            .isInstanceOf(IllegalArgumentException.class);
    }

    @Test void emptyDefinitionsMeanNoModelRequest() throws Exception {
        var planner=new SpringAiToolPlanner(JSON);
        var config=new AiSettingsService.Runtime(AiProviderCatalog.require("qwen"),
            "qwen-plus","test",false);
        assertThat(planner.plan(config,List.of(),List.of())).isEmpty();
    }

    @Test void disallowsUnapprovedNetworkDestinationAndDuplicateDefinitions() {
        assertThatThrownBy(()->new SpringAiToolPlanner(JSON,Map.of("openai",
            URI.create("https://evil.example/v1/chat/completions"))))
            .isInstanceOf(IllegalArgumentException.class);
        var planner=new SpringAiToolPlanner(JSON);
        var config=new AiSettingsService.Runtime(AiProviderCatalog.require("openai"),
            "gpt-4.1-mini","test",false);
        assertThatThrownBy(()->planner.plan(config,List.of(),List.of(FINANCE,FINANCE)))
            .isInstanceOf(IllegalArgumentException.class);
    }
}
