package com.matrix.prp.tasks.model;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import java.time.LocalDate;

public record CreateTaskRequest(
        @NotBlank String moduleCode,
        @NotBlank String title,
        String description,
        @Pattern(regexp = "low|medium|high", message = "must be one of: low, medium, high")
        String priority,
        LocalDate dueDate) {
}
