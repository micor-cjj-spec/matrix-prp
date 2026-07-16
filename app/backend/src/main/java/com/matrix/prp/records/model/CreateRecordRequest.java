package com.matrix.prp.records.model;

import jakarta.validation.constraints.NotBlank;
import java.time.LocalDate;
import java.util.List;

public record CreateRecordRequest(
        @NotBlank String moduleCode,
        @NotBlank String title,
        String content,
        LocalDate recordDate,
        List<Long> tagIds) {
}
