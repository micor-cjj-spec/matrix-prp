package com.matrix.prp.ai;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

public interface CodexJobStore {
    record Job(String id, long userId, String repository, String taskType, String prompt,
        String status, String errorCode, Long approvedBy, LocalDateTime approvedAt,
        LocalDateTime createdAt, LocalDateTime updatedAt) {}

    Job create(long user, String repository, String type, String prompt);
    Optional<Job> find(long user, String id);
    List<Job> list(long user);
    boolean claim(long user, String id, long approver);
    void dispatched(long user, String id);
    void fail(long user, String id, String code);
    boolean cancel(long user, String id);
}
