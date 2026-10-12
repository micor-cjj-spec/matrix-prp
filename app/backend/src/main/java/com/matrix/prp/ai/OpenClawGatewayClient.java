package com.matrix.prp.ai;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

/**
 * Local-only bridge to a separately isolated OpenClaw Gateway instance.
 * Never accept an address, token, agent id, session id or tool policy from the browser.
 * IMPORTANT: OpenClaw shared tokens confer operator authority, hence fail closed.
 */
@Component
public class OpenClawGatewayClient {
    private final ObjectMapper json;
    private final HttpClient http = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER).connectTimeout(Duration.ofSeconds(3)).build();
    private final boolean enabled, isolationConfirmed;
    private final String token;
    private final int port;
    private final String agent;

    public OpenClawGatewayClient(ObjectMapper json,
        @Value("${matrix-prp.ai.openclaw.enabled:false}") boolean enabled,
        @Value("${matrix-prp.ai.openclaw.isolation-confirmed:false}") boolean isolationConfirmed,
        @Value("${matrix-prp.ai.openclaw.gateway-token:}") String token,
        @Value("${matrix-prp.ai.openclaw.port:18789}") int port,
        @Value("${matrix-prp.ai.openclaw.agent-id:prp-planner}") String agent) {
        this.json = json;
        this.enabled = enabled;
        this.isolationConfirmed = isolationConfirmed;
        this.token = token;
        this.port = port;
        this.agent = agent;
    }
    public boolean configured() {
        return enabled && isolationConfirmed && port >= 1 && port <= 65535
            && token != null && token.length() >= 16 && !token.contains("\r") && !token.contains("\n")
            && agent != null && agent.matches("[a-z][a-z0-9-]{0,50}");
    }
    public String generate(AgentTaskStore.AgentTask task) throws Exception {
        if (!configured()) throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
            "OpenClaw isolated Gateway is not enabled");
        URI url = URI.create("http://127.0.0.1:" + port + "/v1/chat/completions");
        String userPrompt = switch (task.taskType()) {
            case "PLAN" -> "Produce a written plan only. Do not take actions.\n\n";
            case "SUMMARIZE" -> "Produce a written summary only. Do not take actions.\n\n";
            case "ANALYZE" -> "Produce a written analysis only. Do not take actions.\n\n";
            default -> throw new IllegalArgumentException("Task type not permitted");
        };
        byte[] bytes = json.writeValueAsBytes(Map.of(
            "model", "openclaw/" + agent,
            "stream", false,
            "user", task.sessionRef(),
            "tool_choice", "none",
            "max_completion_tokens", 1024,
            "messages", List.of(Map.of("role","user","content",userPrompt + task.prompt()))
        ));
        HttpRequest req = HttpRequest.newBuilder(url).timeout(Duration.ofSeconds(90))
            .header("Authorization", "Bearer " + token)
            .header("Content-Type", "application/json")
            .header("Accept", "application/json")
            .POST(HttpRequest.BodyPublishers.ofByteArray(bytes)).build();
        HttpResponse<String> response = http.send(req, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() != 200)
            throw new IllegalStateException("OpenClaw Gateway request rejected");
        if (response.body().length() > 100_000)
            throw new IllegalStateException("OpenClaw output exceeds response limit");
        JsonNode message = json.readTree(response.body()).path("choices").path(0).path("message").path("content");
        if (!message.isTextual() || message.asText().isBlank())
            throw new IllegalStateException("OpenClaw returned no text");
        if (message.asText().length() > 32_000)
            throw new IllegalStateException("OpenClaw text exceeds task result limit");
        return message.asText();
    }
}
