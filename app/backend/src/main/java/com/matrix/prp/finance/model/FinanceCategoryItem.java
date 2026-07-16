package com.matrix.prp.finance.model;

import java.time.OffsetDateTime;

public record FinanceCategoryItem(
        Long id,
        String name,
        String type,
        String color,
        String note,
        OffsetDateTime createdAt) {
}
