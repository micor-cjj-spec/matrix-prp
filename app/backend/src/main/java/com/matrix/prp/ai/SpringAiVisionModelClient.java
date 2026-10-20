package com.matrix.prp.ai;

import java.net.URI;
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.ai.content.Media;
import org.springframework.ai.openai.OpenAiChatModel;
import org.springframework.ai.openai.OpenAiChatOptions;
import org.springframework.ai.openai.api.OpenAiApi;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.retry.policy.NeverRetryPolicy;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.stereotype.Component;
import org.springframework.util.MimeTypeUtils;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.server.ResponseStatusException;

/**
 * Opt-in Spring AI image-only route, using OpenAI-compatible Chat Completions for the
 * explicitly allowed providers. The provider and destination are server-controlled.
 * No tool execution, automatic retry, image persistence, or alternate endpoint.
 */
@Component
public class SpringAiVisionModelClient {
    public record Completion(String answer, long inputTokens, long outputTokens) {}
    private static final Set<String> MIMES = Set.of("image/jpeg", "image/png", "image/webp");
    private final Map<String, URI> testEndpoints;

    public SpringAiVisionModelClient() { this(Map.of()); }

    /** Test-only loopback override, never taken from an authenticated request. */
    SpringAiVisionModelClient(Map<String, URI> testEndpoints) {
        for (var entry : testEndpoints.entrySet()) {
            AiProviderCatalog.require(entry.getKey());
            URI uri = entry.getValue();
            if (!"http".equals(uri.getScheme()) || !"127.0.0.1".equals(uri.getHost()))
                throw new IllegalArgumentException("Only loopback endpoints are permitted");
        }
        this.testEndpoints = Map.copyOf(testEndpoints);
    }

    public Completion complete(AiSettingsService.Runtime config, String model,
            String system, String prompt, byte[] image, String mime) {
        Objects.requireNonNull(config);
        var provider = AiProviderCatalog.require(config.provider().id());
        boolean modelAllowed = switch (provider.id()) {
            case "deepseek" -> "deepseek-flash".equals(model);
            case "openai" -> Set.of("gpt-4.1", "gpt-4.1-mini").contains(model);
            case "kimi", "kimi-global" -> "kimi-k2.5".equals(model);
            default -> false;
        };
        if (!modelAllowed || config.apiKey() == null || config.apiKey().isBlank())
            throw new IllegalArgumentException("Unsupported vision model or credential");
        if (image == null || image.length < 12 || image.length > 3_000_000 ||
                mime == null || !MIMES.contains(mime))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Unsupported image");
        if (system == null || system.isBlank() || system.length() > 5_000 ||
                prompt == null || prompt.isBlank() || prompt.length() > 1_500)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid vision prompt");

        URI endpoint = testEndpoints.getOrDefault(provider.id(), provider.endpoint());
        String origin = endpoint.getScheme() + "://" + endpoint.getRawAuthority();
        var factory = new JdkClientHttpRequestFactory(HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(8))
            .followRedirects(HttpClient.Redirect.NEVER).build());
        factory.setReadTimeout(Duration.ofSeconds(45));
        RestClient.Builder http = RestClient.builder().requestFactory(factory)
            .defaultStatusHandler(HttpStatusCode::isError, (request, response) -> {
                int code = response.getStatusCode().value();
                HttpStatus status = code == 429 ? HttpStatus.TOO_MANY_REQUESTS :
                    code == 503 ? HttpStatus.SERVICE_UNAVAILABLE : HttpStatus.BAD_GATEWAY;
                throw new ResponseStatusException(status, "AI vision provider request failed");
            });

        var api = OpenAiApi.builder().baseUrl(origin)
            .completionsPath(endpoint.getRawPath()).apiKey(config.apiKey())
            .restClientBuilder(http).build();
        var options = OpenAiChatOptions.builder().model(model).maxTokens(2500)
            .internalToolExecutionEnabled(false).build();
        var retry = new RetryTemplate();
        retry.setRetryPolicy(new NeverRetryPolicy());
        var chat = OpenAiChatModel.builder().openAiApi(api).defaultOptions(options)
            .retryTemplate(retry).build();
        var user = UserMessage.builder().text(prompt)
            .media(new Media(MimeTypeUtils.parseMimeType(mime), new ByteArrayResource(image)))
            .build();
        ChatResponse response;
        try {
            response = chat.call(new Prompt(List.of(new SystemMessage(system), user), options));
        } catch (ResponseStatusException e) {
            throw e;
        } catch (RestClientResponseException e) {
            int code = e.getStatusCode().value();
            throw new ResponseStatusException(code == 429 ? HttpStatus.TOO_MANY_REQUESTS :
                code == 503 ? HttpStatus.SERVICE_UNAVAILABLE : HttpStatus.BAD_GATEWAY,
                "AI vision provider request failed");
        } catch (RuntimeException e) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "AI vision provider unavailable");
        }
        if (response == null || response.getResults() == null || response.getResults().isEmpty())
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Empty vision response");
        StringBuilder answer = new StringBuilder();
        for (var generation : response.getResults()) {
            if (generation.getOutput() == null || generation.getOutput().getText() == null) continue;
            String text = generation.getOutput().getText();
            if (answer.length() + text.length() > 20_000)
                throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Vision response too large");
            answer.append(text);
        }
        if (answer.isEmpty())
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Empty vision response");
        var usage = response.getMetadata() == null ? null : response.getMetadata().getUsage();
        long inputTokens = usage == null || usage.getPromptTokens() == null ? 0 :
            usage.getPromptTokens().longValue();
        long outputTokens = usage == null || usage.getCompletionTokens() == null ? 0 :
            usage.getCompletionTokens().longValue();
        return new Completion(answer.toString(), inputTokens, outputTokens);
    }
}
