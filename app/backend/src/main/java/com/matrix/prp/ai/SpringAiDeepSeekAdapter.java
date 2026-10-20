package com.matrix.prp.ai;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Consumer;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.ai.deepseek.DeepSeekChatModel;
import org.springframework.ai.deepseek.DeepSeekChatOptions;
import org.springframework.ai.deepseek.api.DeepSeekApi;
import org.springframework.retry.policy.NeverRetryPolicy;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.stereotype.Component;
import org.springframework.http.HttpStatus;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import org.springframework.web.server.ResponseStatusException;

/** Experimental, owner-scoped DeepSeek transport. Never cache decrypted personal keys. */
@Component
public class SpringAiDeepSeekAdapter {
    private static final String PROVIDER_ENDPOINT = "https://api.deepseek.com";
    private static final int MAX_RESPONSE_CHARS = 32000;
    private final String endpoint;

    public SpringAiDeepSeekAdapter() { this(PROVIDER_ENDPOINT); }

    /** Package-private to allow an isolated loopback mock server in tests. */
    SpringAiDeepSeekAdapter(String endpoint) {
        this.endpoint = Objects.requireNonNull(endpoint);
    }

    public DeepSeekClient.Result stream(AiSettingsService.Runtime config,
            List<DeepSeekClient.ChatMessage> messages, int outputLimit,
            Consumer<String> delta) throws Exception {
        Objects.requireNonNull(config);
        Objects.requireNonNull(messages);
        Objects.requireNonNull(delta);
        if (!config.provider().id().equals("deepseek") || config.legacy())
            throw new IllegalArgumentException("Only personal-key DeepSeek is supported");
        if (!List.of("deepseek-chat", "deepseek-reasoner").contains(config.model()))
            throw new IllegalArgumentException("Unsupported DeepSeek model");
        if (config.apiKey() == null || config.apiKey().isBlank())
            throw new IllegalArgumentException("DeepSeek credentials missing");
        if (outputLimit < 1 || outputLimit > 8192)
            throw new IllegalArgumentException("Invalid output limit");

        List<Message> promptMessages = new ArrayList<>(messages.size());
        for (var message : messages) {
            switch (message.role()) {
                case "system" -> promptMessages.add(new SystemMessage(message.content()));
                case "user" -> promptMessages.add(new UserMessage(message.content()));
                case "assistant" -> promptMessages.add(new AssistantMessage(message.content()));
                default -> throw new IllegalArgumentException("Unsupported prompt role");
            }
        }
        // A fresh model on each call prevents any cross-user key caching.
        DeepSeekApi api = DeepSeekApi.builder().baseUrl(endpoint)
            .apiKey(config.apiKey()).build();
        DeepSeekChatOptions options = DeepSeekChatOptions.builder()
            .model(config.model()).maxTokens(outputLimit).build();
        // Spring AI defaults to a retry policy; prevent all implicit replays
        // because streaming deltas may already have been delivered.
        RetryTemplate singleAttempt = new RetryTemplate();
        singleAttempt.setRetryPolicy(new NeverRetryPolicy());
        DeepSeekChatModel model = DeepSeekChatModel.builder()
            .deepSeekApi(api).defaultOptions(options).retryTemplate(singleAttempt).build();

        StringBuilder answer = new StringBuilder();
        AtomicLong input = new AtomicLong();
        AtomicLong output = new AtomicLong();
        try {
            model.stream(new Prompt(promptMessages, options)).doOnNext(chunk -> {
            if (chunk.getMetadata() != null && chunk.getMetadata().getUsage() != null) {
                var usage = chunk.getMetadata().getUsage();
                if (usage.getPromptTokens() != null)
                    input.set(Math.max(input.get(), usage.getPromptTokens().longValue()));
                if (usage.getCompletionTokens() != null)
                    output.set(Math.max(output.get(), usage.getCompletionTokens().longValue()));
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
            // Retain PRP's existing safe HTTP error contract: 429 is an upstream
            // rate limit, 503 is provider unavailable, others are a bad gateway.
            // Never leak an upstream response body, personal key or raw URL.
            int code = upstream.getStatusCode().value();
            HttpStatus status = code == 429 ? HttpStatus.TOO_MANY_REQUESTS
                : code == 503 ? HttpStatus.SERVICE_UNAVAILABLE : HttpStatus.BAD_GATEWAY;
            throw new ResponseStatusException(status, "AI provider request failed");
        }
        if (answer.isEmpty()) throw new IllegalStateException("AI provider returned an empty response");
        return new DeepSeekClient.Result(answer.toString(), input.get(), output.get());
    }
}
