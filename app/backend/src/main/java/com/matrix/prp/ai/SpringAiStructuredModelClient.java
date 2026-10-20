package com.matrix.prp.ai;

import java.net.URI;
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.springframework.ai.anthropic.AnthropicChatModel;
import org.springframework.ai.anthropic.AnthropicChatOptions;
import org.springframework.ai.anthropic.api.AnthropicApi;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.ai.deepseek.DeepSeekChatModel;
import org.springframework.ai.deepseek.DeepSeekChatOptions;
import org.springframework.ai.deepseek.api.DeepSeekApi;
import org.springframework.ai.openai.OpenAiChatModel;
import org.springframework.ai.openai.OpenAiChatOptions;
import org.springframework.ai.openai.api.OpenAiApi;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.retry.policy.NeverRetryPolicy;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.server.ResponseStatusException;

/** Isolated one-shot text-only Spring AI model calls for validated PRP drafts and practice. */
@Component
public class SpringAiStructuredModelClient {
    public record Completion(String answer, long inputTokens, long outputTokens) {}
    private final Map<String, URI> testEndpoints;

    public SpringAiStructuredModelClient() { this(Map.of()); }

    /** Test-only loopback endpoints, never supplied by users or used by the production bean. */
    SpringAiStructuredModelClient(Map<String, URI> testEndpoints) {
        for (var entry : testEndpoints.entrySet()) {
            AiProviderCatalog.require(entry.getKey());
            URI endpoint = entry.getValue();
            if (!"http".equals(endpoint.getScheme()) || !"127.0.0.1".equals(endpoint.getHost()))
                throw new IllegalArgumentException("Only loopback provider endpoints are permitted");
        }
        this.testEndpoints = Map.copyOf(testEndpoints);
    }

    public Completion complete(AiSettingsService.Runtime config,
            List<DeepSeekClient.ChatMessage> messages, int outputLimit) {
        Objects.requireNonNull(config);
        Objects.requireNonNull(messages);
        var provider = AiProviderCatalog.require(config.provider().id());
        if (!provider.models().contains(config.model()) || config.apiKey() == null
                || config.apiKey().isBlank() || outputLimit < 1 || outputLimit > 8192)
            throw new IllegalArgumentException("Invalid model request");
        if (messages.isEmpty() || messages.size() > 24)
            throw new IllegalArgumentException("Invalid message count");
        List<Message> promptMessages = new ArrayList<>(messages.size());
        for (var m : messages) {
            if (m.content() == null || m.content().length() > 16000)
                throw new IllegalArgumentException("Model message exceeds limit");
            switch (m.role()) {
                case "system" -> promptMessages.add(new SystemMessage(m.content()));
                case "user" -> promptMessages.add(new UserMessage(m.content()));
                case "assistant" -> promptMessages.add(new AssistantMessage(m.content()));
                default -> throw new IllegalArgumentException("Unsupported message role");
            }
        }

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
                throw new ResponseStatusException(status, "AI provider request failed");
            });
        RetryTemplate oneAttempt = new RetryTemplate();
        oneAttempt.setRetryPolicy(new NeverRetryPolicy());
        ChatModel model;
        Prompt prompt;
        if (provider.id().equals("deepseek")) {
            var api = DeepSeekApi.builder().baseUrl(origin)
                .completionsPath(endpoint.getRawPath()).apiKey(config.apiKey())
                .restClientBuilder(http).build();
            var options = DeepSeekChatOptions.builder().model(config.model())
                .maxTokens(outputLimit).build();
            model = DeepSeekChatModel.builder().deepSeekApi(api)
                .defaultOptions(options).retryTemplate(oneAttempt).build();
            prompt = new Prompt(promptMessages, options);
        } else if (provider.anthropic()) {
            var api = AnthropicApi.builder().baseUrl(origin)
                .completionsPath(endpoint.getRawPath()).apiKey(config.apiKey())
                .restClientBuilder(http).build();
            var options = AnthropicChatOptions.builder().model(config.model())
                .maxTokens(outputLimit).build();
            model = AnthropicChatModel.builder().anthropicApi(api)
                .defaultOptions(options).retryTemplate(oneAttempt).build();
            prompt = new Prompt(promptMessages, options);
        } else {
            var api = OpenAiApi.builder().baseUrl(origin)
                .completionsPath(endpoint.getRawPath()).apiKey(config.apiKey())
                .restClientBuilder(http).build();
            var options = OpenAiChatOptions.builder().model(config.model())
                .maxTokens(outputLimit).build();
            model = OpenAiChatModel.builder().openAiApi(api)
                .defaultOptions(options).retryTemplate(oneAttempt).build();
            prompt = new Prompt(promptMessages, options);
        }
        org.springframework.ai.chat.model.ChatResponse response;
        try {
            response = model.call(prompt);
        } catch (ResponseStatusException e) {
            throw e;
        } catch (RestClientResponseException e) {
            int code = e.getStatusCode().value();
            throw new ResponseStatusException(code == 429 ? HttpStatus.TOO_MANY_REQUESTS :
                code == 503 ? HttpStatus.SERVICE_UNAVAILABLE : HttpStatus.BAD_GATEWAY,
                "AI provider request failed");
        } catch (RuntimeException e) {
            // No provider-supplied error body, prompt or key in the API response.
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,"AI provider is unavailable");
        }
        if (response == null || response.getResults() == null ||
                response.getResults().isEmpty())
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,"AI provider returned an empty response");
        StringBuilder answer = new StringBuilder();
        for (var generation : response.getResults()) {
            if (generation.getOutput() == null) continue;
            String text = generation.getOutput().getText();
            if (text == null || text.isEmpty()) continue;
            if (answer.length() + text.length() > 20000)
                throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,"AI response exceeds limit");
            answer.append(text);
        }
        if (answer.isEmpty())
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,"AI provider returned an empty response");
        var usage = response.getMetadata() == null ? null : response.getMetadata().getUsage();
        long input = usage == null || usage.getPromptTokens() == null ? 0L :
            usage.getPromptTokens().longValue();
        long output = usage == null || usage.getCompletionTokens() == null ? 0L :
            usage.getCompletionTokens().longValue();
        return new Completion(answer.toString(),input,output);
    }
}
