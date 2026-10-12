package com.matrix.prp.ai;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

/** Streaming adapter. Provider URLs are fixed in the catalog; no custom host or redirect credentials. */
@Component
public class AiProviderClient {
    private final ObjectMapper json;
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(8))
        .followRedirects(HttpClient.Redirect.NEVER).build();

    public AiProviderClient(ObjectMapper json) { this.json = json; }

    public DeepSeekClient.Result stream(AiSettingsService.Runtime config, List<DeepSeekClient.ChatMessage> messages,
                                       int outputLimit, Consumer<String> delta) throws Exception {
        AiProviderCatalog.Provider provider = config.provider();
        byte[] body;
        if (provider.anthropic()) {
            // Anthropic accepts system instructions as a top-level field, not as a message role.
            String system = messages.stream().filter(m -> m.role().equals("system"))
                .map(DeepSeekClient.ChatMessage::content).reduce((a,b) -> a + "\n" + b).orElse("");
            List<DeepSeekClient.ChatMessage> chatMessages = messages.stream()
                .filter(m -> !m.role().equals("system")).toList();
            body = json.writeValueAsBytes(Map.of(
                "model", config.model(), "max_tokens", outputLimit, "system", system,
                "messages", chatMessages, "stream", true));
        } else {
            Map<String, Object> payload = new java.util.LinkedHashMap<>();
            payload.put("model", config.model());
            payload.put("messages", messages);
            payload.put("stream", true);
            payload.put("max_tokens", outputLimit);
            if (provider.id().equals("deepseek") || provider.id().equals("openai"))
                payload.put("stream_options", Map.of("include_usage", true));
            body = json.writeValueAsBytes(payload);
        }
        HttpRequest.Builder request = HttpRequest.newBuilder(provider.endpoint())
            .timeout(Duration.ofSeconds(150))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofByteArray(body));
        if (provider.anthropic()) {
            request.header("x-api-key", config.apiKey()).header("anthropic-version", "2023-06-01");
        } else {
            request.header("Authorization", "Bearer " + config.apiKey());
        }
        HttpResponse<java.io.InputStream> response = http.send(request.build(), HttpResponse.BodyHandlers.ofInputStream());
        if (response.statusCode() != 200) {
            response.body().close();
            HttpStatus status = response.statusCode() == 429 ? HttpStatus.TOO_MANY_REQUESTS :
                response.statusCode() == 401 || response.statusCode() == 403 ? HttpStatus.BAD_GATEWAY :
                HttpStatus.BAD_GATEWAY;
            throw new ResponseStatusException(status, "AI provider request failed (" + response.statusCode() + ")");
        }
        StringBuilder answer = new StringBuilder();
        long input = 0, output = 0;
        boolean finished = false;
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(response.body(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (Thread.currentThread().isInterrupted()) throw new InterruptedException("AI request interrupted");
                if (!line.startsWith("data:")) continue;
                String data = line.substring(5).trim();
                if (data.equals("[DONE]")) { finished = true; break; }
                if (data.isEmpty()) continue;
                JsonNode event = json.readTree(data);
                if (provider.anthropic()) {
                    String type = event.path("type").asText();
                    if (type.equals("error")) throw new IllegalStateException("Provider stream error");
                    if (type.equals("message_stop")) { finished = true; break; }
                    if (type.equals("message_start"))
                        input = event.path("message").path("usage").path("input_tokens").asLong(input);
                    if (type.equals("message_delta"))
                        output = event.path("usage").path("output_tokens").asLong(output);
                    JsonNode chunk = event.path("delta").path("text");
                    if (type.equals("content_block_delta") && chunk.isTextual())
                        append(answer, chunk.asText(), delta);
                } else {
                    if (event.hasNonNull("error")) throw new IllegalStateException("Provider stream error");
                    JsonNode usage = event.path("usage");
                    if (usage.isObject()) {
                        input = usage.path("prompt_tokens").asLong(input);
                        output = usage.path("completion_tokens").asLong(output);
                    }
                    JsonNode chunk = event.path("choices").path(0).path("delta").path("content");
                    if (chunk.isTextual()) append(answer, chunk.asText(), delta);
                }
            }
        }
        if (!finished || answer.isEmpty())
            throw new IllegalStateException("AI provider stream ended without a complete response");
        return new DeepSeekClient.Result(answer.toString(), input, output);
    }
    private static void append(StringBuilder answer, String part, Consumer<String> delta) {
        if (part.isEmpty()) return;
        if (answer.length() + part.length() > 32000)
            throw new IllegalStateException("AI response exceeds output limit");
        answer.append(part);
        delta.accept(part);
    }
}
