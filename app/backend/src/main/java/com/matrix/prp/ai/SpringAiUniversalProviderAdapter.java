package com.matrix.prp.ai;

import java.net.URI;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Consumer;
import org.springframework.ai.anthropic.AnthropicChatModel;
import org.springframework.ai.anthropic.AnthropicChatOptions;
import org.springframework.ai.anthropic.api.AnthropicApi;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.ai.openai.OpenAiChatModel;
import org.springframework.ai.openai.OpenAiChatOptions;
import org.springframework.ai.openai.api.OpenAiApi;
import org.springframework.http.HttpStatus;
import org.springframework.retry.policy.NeverRetryPolicy;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import org.springframework.web.server.ResponseStatusException;

/**
 * All non-DeepSeek PRP provider transports via Spring AI.
 * Provider destinations are allowlisted in AiProviderCatalog; models and
 * plaintext personal keys are per-request and never cached or logged.
 */
@Component
public class SpringAiUniversalProviderAdapter {
    private static final int MAX_RESPONSE_CHARS = 32000;
    private final Map<String, URI> testEndpoints;

    public SpringAiUniversalProviderAdapter() { this(Map.of()); }

    /** Test-only endpoints must be loopback. Never used by the production bean. */
    SpringAiUniversalProviderAdapter(Map<String, URI> testEndpoints) {
        for (var entry : testEndpoints.entrySet()) {
            AiProviderCatalog.require(entry.getKey());
            URI endpoint = entry.getValue();
            if (!"http".equals(endpoint.getScheme()) || !"127.0.0.1".equals(endpoint.getHost()))
                throw new IllegalArgumentException("Only loopback test provider endpoints allowed");
        }
        this.testEndpoints = Map.copyOf(testEndpoints);
    }

    public DeepSeekClient.Result stream(AiSettingsService.Runtime config,
             List<DeepSeekClient.ChatMessage> messages, int outputLimit,
             Consumer<String> delta) {
        Objects.requireNonNull(config);
        Objects.requireNonNull(messages);
        Objects.requireNonNull(delta);
        String providerId = config.provider().id();
        if ("deepseek".equals(providerId))
            throw new IllegalArgumentException("DeepSeek has a dedicated Spring AI adapter");
        // Do not trust or use a runtime-provided endpoint. Resolve the fixed
        // URL from the server's allowlist (test loopback replacement is isolated).
        URI endpoint = testEndpoints.getOrDefault(providerId,
            AiProviderCatalog.require(providerId).endpoint());
        if (config.apiKey() == null || config.apiKey().isBlank())
            throw new IllegalArgumentException("Provider API key missing");
        if (!config.provider().models().contains(config.model()))
            throw new IllegalArgumentException("Unsupported provider/model pair");
        if (outputLimit < 1 || outputLimit > 8192)
            throw new IllegalArgumentException("Invalid output limit");

        List<Message> promptMessages = new ArrayList<>(messages.size());
        for (var message : messages) {
            switch (message.role()) {
                case "system" -> promptMessages.add(new SystemMessage(message.content()));
                case "user" -> promptMessages.add(new UserMessage(message.content()));
                case "assistant" -> promptMessages.add(new AssistantMessage(message.content()));
                default -> throw new IllegalArgumentException("Unsupported chat role");
            }
        }

        boolean anthropic = config.provider().anthropic();
        // Anthropic's SSE completion is "event: message_stop"; the OpenAI
        // compatible endpoints use a "data: [DONE]" sentinel.
        DeepSeekStreamCompletionProbe completion = new DeepSeekStreamCompletionProbe(
            anthropic ? "event: message_stop" : "data: [DONE]");
        WebClient.Builder webClient = WebClient.builder().filter((request, next) ->
            next.exchange(request).map(response -> response.mutate()
                .body(body -> body.doOnNext(completion::inspect)).build()));

        RetryTemplate singleAttempt = new RetryTemplate();
        singleAttempt.setRetryPolicy(new NeverRetryPolicy());
        String baseUrl = endpoint.getScheme() + "://" + endpoint.getRawAuthority();
        ChatModel model;
        Prompt prompt;
        if (anthropic) {
            AnthropicApi api = AnthropicApi.builder().baseUrl(baseUrl)
                .completionsPath(endpoint.getRawPath()).apiKey(config.apiKey())
                .webClientBuilder(webClient).build();
            AnthropicChatOptions options = AnthropicChatOptions.builder()
                .model(config.model()).maxTokens(outputLimit).build();
            model = AnthropicChatModel.builder().anthropicApi(api)
                .defaultOptions(options).retryTemplate(singleAttempt).build();
            prompt = new Prompt(promptMessages, options);
        } else {
            OpenAiApi api = OpenAiApi.builder().baseUrl(baseUrl)
                .completionsPath(endpoint.getRawPath()).apiKey(config.apiKey())
                .webClientBuilder(webClient).build();
            OpenAiChatOptions options = OpenAiChatOptions.builder()
                .model(config.model()).maxTokens(outputLimit).build();
            model = OpenAiChatModel.builder().openAiApi(api)
                .defaultOptions(options).retryTemplate(singleAttempt).build();
            prompt = new Prompt(promptMessages, options);
        }

        StringBuilder answer = new StringBuilder();
        AtomicLong inputTokens = new AtomicLong(), outputTokens = new AtomicLong();
        try {
            model.stream(prompt).doOnNext(chunk -> {
                if (chunk.getMetadata() != null && chunk.getMetadata().getUsage() != null) {
                    var usage = chunk.getMetadata().getUsage();
                    if (usage.getPromptTokens() != null)
                        inputTokens.set(Math.max(inputTokens.get(), usage.getPromptTokens().longValue()));
                    if (usage.getCompletionTokens() != null)
                        outputTokens.set(Math.max(outputTokens.get(), usage.getCompletionTokens().longValue()));
                }
                if (chunk.getResult() == null || chunk.getResult().getOutput() == null) return;
                String part = chunk.getResult().getOutput().getText();
                if (part == null || part.isEmpty()) return;
                if (answer.length() + part.length() > MAX_RESPONSE_CHARS)
                    throw new IllegalStateException("AI response exceeds output limit");
                answer.append(part);
                delta.accept(part);
            }).blockLast(Duration.ofSeconds(145));
        } catch (WebClientResponseException upstream) {
            int code = upstream.getStatusCode().value();
            HttpStatus status = code == 429 ? HttpStatus.TOO_MANY_REQUESTS :
                code == 503 ? HttpStatus.SERVICE_UNAVAILABLE : HttpStatus.BAD_GATEWAY;
            // Intentionally hide body, prompt, key and upstream URL.
            throw new ResponseStatusException(status, "AI provider request failed");
        }
        completion.requireDone();
        if (answer.isEmpty()) throw new IllegalStateException("AI provider returned an empty response");
        return new DeepSeekClient.Result(answer.toString(), inputTokens.get(), outputTokens.get());
    }
}
