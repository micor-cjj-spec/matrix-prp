package com.matrix.prp.ai;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.server.ResponseStatusException;

/** One bounded provider-native function-calling turn; no tool execution occurs in this component. */
@Component
public class AiToolPlanner {
    public record Call(String name, JsonNode arguments) {}
    private final ObjectMapper mapper;
    private final SpringAiToolPlanner springAi;
    private final boolean springAiEnabled;
    private final HttpClient http=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(8))
        .followRedirects(HttpClient.Redirect.NEVER).build();
    /** Tests and emergency legacy path keep the previous constructor. */
    public AiToolPlanner(ObjectMapper mapper) { this(mapper,null,false); }
    @Autowired
    public AiToolPlanner(ObjectMapper mapper, SpringAiToolPlanner springAi,
            @Value("${matrix-prp.ai.spring-ai.tools-enabled:true}") boolean enabled) {
        this.mapper=mapper;
        this.springAi=springAi;
        this.springAiEnabled=enabled;
    }
    public List<Call> plan(AiSettingsService.Runtime config, List<DeepSeekClient.ChatMessage> messages,
                           List<AiToolRegistry.Definition> definitions) throws Exception {
        if (definitions.isEmpty()) return List.of();
        // This only selects tool *proposals*. Execution, scopes and audit
        // still belong solely to AiToolRegistry / AiService after consent.
        if (springAiEnabled) {
            if (springAi == null) throw new IllegalStateException("Spring AI tool planner unavailable");
            return springAi.plan(config,messages,definitions);
        }
        var provider=config.provider();
        Map<String,Object> payload=new LinkedHashMap<>();
        payload.put("model",config.model()); payload.put("stream",false); payload.put("max_tokens",768);
        if(provider.anthropic()) {
            String system=messages.stream().filter(m->m.role().equals("system"))
                .map(DeepSeekClient.ChatMessage::content).reduce((a,b)->a+"\n"+b).orElse("");
            payload.put("system",system);
            payload.put("messages",messages.stream().filter(m->!m.role().equals("system")).toList());
            payload.put("tools",definitions.stream().map(t->Map.of("name",t.name(),
                "description",t.description(),"input_schema",t.parameters())).toList());
        } else {
            payload.put("messages",messages);
            payload.put("tools",definitions.stream().map(t->Map.of("type","function",
                "function",Map.of("name",t.name(),"description",t.description(),
                    "parameters",t.parameters()))).toList());
            payload.put("tool_choice","auto");
        }
        HttpRequest.Builder builder=HttpRequest.newBuilder(provider.endpoint()).timeout(Duration.ofSeconds(35))
            .header("Content-Type","application/json").POST(HttpRequest.BodyPublishers.ofByteArray(mapper.writeValueAsBytes(payload)));
        if(provider.anthropic()) builder.header("x-api-key",config.apiKey())
            .header("anthropic-version","2023-06-01");
        else builder.header("Authorization","Bearer "+config.apiKey());
        HttpResponse<String> response=http.send(builder.build(),HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        if(response.statusCode()!=200)
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,"Provider tool selection unavailable");
        return parse(mapper.readTree(response.body()),provider.anthropic());
    }
    List<Call> parse(JsonNode root,boolean anthropic) throws Exception {
        List<Call> calls=new ArrayList<>();
        JsonNode chunks=anthropic?root.path("content"):root.path("choices").path(0).path("message").path("tool_calls");
        if (!chunks.isArray()) return List.of();
        for(JsonNode node:chunks) {
            String name;
            JsonNode arguments;
            if(anthropic) {
                if(!"tool_use".equals(node.path("type").asText())) continue;
                name=node.path("name").asText();
                arguments=node.path("input");
            } else {
                if(!"function".equals(node.path("type").asText())) continue;
                name=node.path("function").path("name").asText();
                String argumentText=node.path("function").path("arguments").asText("{}");
                if(argumentText.length()>2000) throw new IllegalArgumentException("Oversized tool arguments");
                arguments=mapper.readTree(argumentText);
            }
            if(name.isBlank() || arguments==null || !arguments.isObject())
                throw new IllegalArgumentException("Invalid model tool call");
            calls.add(new Call(name,arguments));
            if(calls.size()>4) throw new IllegalArgumentException("Too many tool calls");
        }
        return calls;
    }
}
