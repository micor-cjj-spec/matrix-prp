package com.matrix.prp.ai;

import com.matrix.prp.ai.AiStore.Conversation;
import com.matrix.prp.ai.AiStore.Message;
import com.matrix.prp.ai.AiStore.Usage;
import com.matrix.prp.auth.security.CurrentUser;
import java.nio.charset.StandardCharsets;
import java.time.YearMonth;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.task.TaskExecutor;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.web.server.ResponseStatusException;

@Service
public class AiService {
    private final AiStore store;
    private final DeepSeekClient deepSeek;
    private final TaskExecutor executor;
    private final int outputLimit, perUserRequests, globalRequests;
    private final long perUserTokens, globalTokens;

    public AiService(AiStore store, DeepSeekClient deepSeek, @Qualifier("aiExecutor") TaskExecutor executor,
                     @Value("${matrix-prp.ai.max-output-tokens:1024}") int outputLimit,
                     @Value("${matrix-prp.ai.user-monthly-requests:200}") int perUserRequests,
                     @Value("${matrix-prp.ai.global-monthly-requests:1000}") int globalRequests,
                     @Value("${matrix-prp.ai.user-monthly-reserved-tokens:250000}") long perUserTokens,
                     @Value("${matrix-prp.ai.global-monthly-reserved-tokens:1000000}") long globalTokens) {
        this.store = store;
        this.deepSeek = deepSeek;
        this.executor = executor;
        this.outputLimit = outputLimit;
        this.perUserRequests = perUserRequests;
        this.globalRequests = globalRequests;
        this.perUserTokens = perUserTokens;
        this.globalTokens = globalTokens;
    }

    public List<Conversation> conversations() { return store.list(CurrentUser.id()); }
    public List<Message> messages(String id) {
        long user = CurrentUser.id();
        ensureOwner(user, id);
        return store.messages(user, id);
    }
    public Map<String, Object> usage() {
        Usage current = store.usage(CurrentUser.id(), month());
        return Map.of("month", current.month(), "requests", current.requests(),
                "reservedTokens", current.reservedTokens(), "inputTokens", current.inputTokens(),
                "outputTokens", current.outputTokens(), "maxRequests", perUserRequests,
                "maxReservedTokens", perUserTokens);
    }

    public SseEmitter chat(String id, String prompt) {
        long user = CurrentUser.id();
        String content = prompt == null ? "" : prompt.trim();
        if (content.isEmpty() || content.length() > 4000)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Message must be 1-4000 characters");
        if (id != null && !id.isBlank()) ensureOwner(user, id);
        deepSeek.requireConfigured();
        List<DeepSeekClient.ChatMessage> history = new ArrayList<>();
        if (id != null && !id.isBlank()) {
            List<Message> previous = store.messages(user, id);
            int start = Math.max(0, previous.size() - 12);
            for (Message message : previous.subList(start, previous.size()))
                if (message.role().equals("user") || message.role().equals("assistant"))
                    history.add(new DeepSeekClient.ChatMessage(message.role(), message.content()));
        }
        history.add(new DeepSeekClient.ChatMessage("user", content));
        while (history.size() > 1 && estimatedInput(history) > 16000) history.removeFirst();
        long reserved = estimatedInput(history) + outputLimit + 256L;
        String month = month();
        store.reserve(user, month, reserved, perUserRequests, perUserTokens, globalRequests, globalTokens);
        Conversation conversation = id == null || id.isBlank() ?
                store.create(user, content.substring(0, Math.min(70, content.length()))) : null;
        String conversationId = conversation == null ? id : conversation.id();
        store.append(user, conversationId, "user", content);
        SseEmitter emitter = new SseEmitter(155_000L);
        try {
            executor.execute(() -> {
                try {
                    send(emitter, "meta", Map.of("conversationId", conversationId, "model", deepSeek.model()));
                    DeepSeekClient.Result result = deepSeek.stream(history, outputLimit,
                            part -> send(emitter, "delta", Map.of("text", part)));
                    store.append(user, conversationId, "assistant", result.answer());
                    store.completed(user, month, result.inputTokens(), result.outputTokens());
                    send(emitter, "done", Map.of("conversationId", conversationId,
                            "inputTokens", result.inputTokens(), "outputTokens", result.outputTokens()));
                    emitter.complete();
                } catch (Exception ex) {
                    try { send(emitter, "error", Map.of("message", "AI request failed. Please retry.")); }
                    catch (Exception ignored) { /* client disconnected */ }
                    emitter.complete();
                }
            });
        } catch (RuntimeException ex) {
            emitter.completeWithError(ex);
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "AI workers are busy");
        }
        return emitter;
    }

    private static long estimatedInput(List<DeepSeekClient.ChatMessage> history) {
        return history.stream().mapToLong(m -> m.content().getBytes(StandardCharsets.UTF_8).length + 20L).sum();
    }
    private static String month() { return YearMonth.now(ZoneOffset.UTC).toString(); }
    private void ensureOwner(long user, String id) {
        if (!store.owns(user, id))
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Conversation not found");
    }
    private static void send(SseEmitter emitter, String event, Object data) {
        try { emitter.send(SseEmitter.event().name(event).data(data)); }
        catch (java.io.IOException e) { throw new IllegalStateException("Client disconnected", e); }
    }
}
