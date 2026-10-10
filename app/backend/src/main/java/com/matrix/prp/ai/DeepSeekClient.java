package com.matrix.prp.ai;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

/** Access to the fixed upstream host; never expose the secret to browser clients. */
@Component
public class DeepSeekClient {
    public record ChatMessage(String role, String content) {}
    public record Result(String answer, long inputTokens, long outputTokens) {}
    private final ObjectMapper mapper;
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(8)).build();
    private final String apiKey;
    private final String model;

    public DeepSeekClient(ObjectMapper mapper,
                          @Value("${matrix-prp.ai.deepseek.api-key:}") String apiKey,
                          @Value("${matrix-prp.ai.deepseek.model:deepseek-chat}") String model) {
        this.mapper = mapper;
        this.apiKey = apiKey;
        if (!List.of("deepseek-chat", "deepseek-reasoner").contains(model))
            throw new IllegalArgumentException("Unsupported DeepSeek model");
        this.model = model;
    }

    public String model() { return model; }
    public void requireConfigured() {
        if (apiKey == null || apiKey.isBlank())
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "DeepSeek is not configured");
    }

    public Result stream(List<ChatMessage> messages, int maxOutputTokens, Consumer<String> delta) throws Exception {
        requireConfigured();
        byte[] body = mapper.writeValueAsBytes(Map.of(
                "model", model, "messages", messages, "stream", true,
                "stream_options", Map.of("include_usage", true),
                "max_tokens", maxOutputTokens));
        HttpRequest request = HttpRequest.newBuilder(URI.create("https://api.deepseek.com/chat/completions"))
                .timeout(Duration.ofSeconds(150))
                .header("Authorization", "Bearer " + apiKey)
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofByteArray(body)).build();
        HttpResponse<java.io.InputStream> response = http.send(request, HttpResponse.BodyHandlers.ofInputStream());
        if (response.statusCode() != 200) {
            response.body().close();
            throw new ResponseStatusException(response.statusCode() == 429 ?
                    HttpStatus.TOO_MANY_REQUESTS : HttpStatus.BAD_GATEWAY, "AI provider request failed");
        }
        StringBuilder answer = new StringBuilder();
        long input = 0, output = 0;
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(response.body(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (Thread.currentThread().isInterrupted()) throw new InterruptedException("AI request interrupted");
                if (!line.startsWith("data:")) continue;
                String data = line.substring(5).trim();
                if (data.equals("[DONE]")) break;
                if (data.isEmpty()) continue;
                JsonNode event = mapper.readTree(data);
                JsonNode usage = event.path("usage");
                if (!usage.isMissingNode() && !usage.isNull()) {
                    input = usage.path("prompt_tokens").asLong(input);
                    output = usage.path("completion_tokens").asLong(output);
                }
                JsonNode chunk = event.path("choices").path(0).path("delta").path("content");
                if (chunk.isTextual() && !chunk.asText().isEmpty()) {
                    String part = chunk.asText();
                    if (answer.length() + part.length() > 32000)
                        throw new IllegalStateException("AI response exceeds output limit");
                    answer.append(part);
                    delta.accept(part);
                }
            }
        }
        if (answer.isEmpty()) throw new IllegalStateException("AI provider returned an empty response");
        return new Result(answer.toString(), input, output);
    }
}
