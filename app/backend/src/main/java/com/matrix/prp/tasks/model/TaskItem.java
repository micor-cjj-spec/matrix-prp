package com.matrix.prp.tasks.model;

import java.time.LocalDate;
import java.time.OffsetDateTime;

public record TaskItem(
        long id,
        String moduleCode,
        String title,
        String description,
        String priority,
        String status,
        LocalDate dueDate,
        OffsetDateTime createdAt,
        OffsetDateTime completedAt) {
}
