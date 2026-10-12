package com.matrix.prp.ai;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

public interface AgentTaskStore {
    record AgentTask(String id, long userId, String taskType, String prompt, String status,
        String result, String errorCode, LocalDateTime createdAt, LocalDateTime updatedAt,
        Long approvedBy, LocalDateTime approvedAt, String sessionRef) {}

    AgentTask create(long user, String type, String prompt);
    Optional<AgentTask> find(long user, String id);
    List<AgentTask> list(long user);
    /** Atomically claim a pending task; approval must not replay an upstream request. */
    boolean claim(long user, String id, long approver);
    void complete(long user, String id, String result);
    void fail(long user, String id, String errorCode);
    boolean cancel(long user, String id);
}
