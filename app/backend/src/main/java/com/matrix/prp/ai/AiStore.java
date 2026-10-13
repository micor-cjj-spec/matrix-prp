package com.matrix.prp.ai;

import java.time.LocalDateTime;
import java.util.List;

public interface AiStore {
    record Conversation(String id, String title, LocalDateTime updatedAt) {}
    record Message(long id, String role, String content, LocalDateTime createdAt) {}
    record Usage(String month, int requests, long reservedTokens, long inputTokens, long outputTokens) {}

    Conversation create(long userId, String title);
    List<Conversation> list(long userId);
    boolean owns(long userId, String conversationId);
    default List<Message> messages(long userId, String conversationId) {
        return messages(userId, conversationId, null, 200);
    }
    /** Newest page in chronological order; beforeId is an exclusive message cursor. */
    List<Message> messages(long userId, String conversationId, Long beforeId, int limit);
    void append(long userId, String conversationId, String role, String content);
    void reserve(long userId, String month, long tokens, int perUserRequests, long perUserTokens,
                 int globalRequests, long globalTokens);
    void completed(long userId, String month, long inputTokens, long outputTokens);
    Usage usage(long userId, String month);
}
