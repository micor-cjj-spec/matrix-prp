package com.matrix.prp.ai;

import java.time.Clock;
import java.time.LocalDateTime;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

/** Test profile implementation with the same user/time visibility rules. */
@Component
@Profile("test")
public class InMemoryAiInvocationAudit implements AiInvocationAudit {
    private final CopyOnWriteArrayList<Entry> entries = new CopyOnWriteArrayList<>();

    @Override public void record(Entry entry) { entries.add(entry); }

    private List<Entry> scoped(long userId, int days) {
        LocalDateTime since = LocalDateTime.now(Clock.systemUTC()).minusDays(days);
        return entries.stream().filter(e -> e.userId()==userId && !e.occurredAt().isBefore(since))
            .sorted(Comparator.comparing(Entry::occurredAt).reversed()).toList();
    }

    @Override public List<Detail> recent(long userId, int days, int limit) {
        return scoped(userId, days).stream().limit(limit).map(AiInvocationAudit::detail).toList();
    }

    @Override public Summary summary(long userId, int days) {
        var items = scoped(userId, days);
        long success = items.stream().filter(e -> e.status().equals("SUCCESS")).count();
        long failure = items.stream().filter(e -> e.status().equals("FAILURE")).count();
        var duration = items.stream().mapToLong(Entry::elapsedMs).average();
        var firstToken = items.stream().filter(e -> e.firstTokenMs()!=null)
            .mapToLong(Entry::firstTokenMs).average();
        long missing = items.stream().filter(e -> e.inputTokens()==null || e.outputTokens()==null).count();
        return new Summary(items.size(), success, failure,
            duration.isPresent() ? Math.round(duration.getAsDouble()) : null,
            firstToken.isPresent() ? Math.round(firstToken.getAsDouble()) : null,
            items.stream().mapToLong(e -> e.inputTokens()==null?0:e.inputTokens()).sum(),
            items.stream().mapToLong(e -> e.outputTokens()==null?0:e.outputTokens()).sum(),
            missing);
    }
}
