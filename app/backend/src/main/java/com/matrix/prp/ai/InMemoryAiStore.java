package com.matrix.prp.ai;

import java.time.LocalDateTime;
import java.util.*;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Repository;
import org.springframework.web.server.ResponseStatusException;

@Repository
@Profile("test")
public class InMemoryAiStore implements AiStore {
    private record Owned(long userId, Conversation conversation) {}
    private final Map<String, Owned> conversations = new HashMap<>();
    private final Map<String, List<Message>> messages = new HashMap<>();
    private final Map<String, Usage> usage = new HashMap<>();
    private long nextId = 1;

    @Override public synchronized Conversation create(long user, String title) {
        Conversation item = new Conversation(UUID.randomUUID().toString(), title, LocalDateTime.now());
        conversations.put(item.id(), new Owned(user, item));
        messages.put(item.id(), new ArrayList<>());
        return item;
    }
    @Override public synchronized List<Conversation> list(long user) {
        return conversations.values().stream().filter(c -> c.userId == user).map(Owned::conversation).toList();
    }
    @Override public synchronized boolean owns(long user, String id) {
        Owned c = conversations.get(id);
        return c != null && c.userId == user;
    }
    @Override public synchronized List<Message> messages(long user, String id) {
        if (!owns(user, id)) return List.of();
        return List.copyOf(messages.get(id));
    }
    @Override public synchronized void append(long user, String id, String role, String content) {
        if (!owns(user, id)) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Conversation not found");
        messages.get(id).add(new Message(nextId++, role, content, LocalDateTime.now()));
    }
    @Override public synchronized void reserve(long user, String month, long tokens, int userReq, long userTokens,
                                               int globalReq, long globalTokens) {
        String global = "0:"+month, own = user+":"+month;
        Usage g = usage.getOrDefault(global, new Usage(month, 0, 0, 0, 0));
        Usage u = usage.getOrDefault(own, new Usage(month, 0, 0, 0, 0));
        if (g.requests() >= globalReq || g.reservedTokens() + tokens > globalTokens ||
                u.requests() >= userReq || u.reservedTokens() + tokens > userTokens)
            throw new ResponseStatusException(HttpStatus.TOO_MANY_REQUESTS, "Monthly AI allowance reached");
        usage.put(global, new Usage(month, g.requests()+1, g.reservedTokens()+tokens, g.inputTokens(), g.outputTokens()));
        usage.put(own, new Usage(month, u.requests()+1, u.reservedTokens()+tokens, u.inputTokens(), u.outputTokens()));
    }
    @Override public synchronized void completed(long user, String month, long in, long out) {
        for (String k : List.of("0:"+month, user+":"+month)) {
            Usage v = usage.get(k);
            if (v != null) usage.put(k, new Usage(month, v.requests(), v.reservedTokens(), v.inputTokens()+in, v.outputTokens()+out));
        }
    }
    @Override public synchronized Usage usage(long user, String month) {
        return usage.getOrDefault(user+":"+month, new Usage(month,0,0,0,0));
    }
}
