package com.matrix.prp.tasks.model;

import java.time.LocalDate;

public record TaskFilter(
        String status,
        String moduleCode,
        LocalDate dueDate,
        String priority) {
}
