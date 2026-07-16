package com.matrix.prp.finance.model;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public record CreateFinanceCategoryRequest(
        @NotBlank String name,
        @Pattern(regexp = "income|expense", message = "must be one of: income, expense")
        @NotBlank String type,
        String color,
        String note) {
}
