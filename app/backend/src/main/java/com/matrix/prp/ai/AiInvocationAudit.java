package com.matrix.prp.ai;

import java.time.LocalDateTime;
import java.util.List;

/** Strictly metadata-only model invocation audit; no prompts, output, keys or tool results. */
public interface AiInvocationAudit {
    record Entry(long userId, String provider, String model, String credentialSource,
                 String status, String failureCategory, long elapsedMs, Long firstTokenMs,
                 Long inputTokens, Long outputTokens, LocalDateTime occurredAt) {}
    record Detail(String provider, String model, String credentialSource, String status,
                  String failureCategory, long elapsedMs, Long firstTokenMs,
                  Long inputTokens, Long outputTokens, LocalDateTime occurredAt) {}
    record Summary(long totalRequests, long successfulRequests, long failedRequests,
                   Long averageElapsedMs, Long averageFirstTokenMs,
                   long inputTokens, long outputTokens, long unreportedUsageRequests) {}
    record Report(Summary summary, List<Detail> recent, String costStatus) {}

    void record(Entry entry);
    List<Detail> recent(long userId, int days, int limit);
    Summary summary(long userId, int days);

    static Detail detail(Entry entry) {
        return new Detail(entry.provider(), entry.model(), entry.credentialSource(),
            entry.status(), entry.failureCategory(), entry.elapsedMs(), entry.firstTokenMs(),
            entry.inputTokens(), entry.outputTokens(), entry.occurredAt());
    }
}
