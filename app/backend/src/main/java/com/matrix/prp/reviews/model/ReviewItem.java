package com.matrix.prp.reviews.model;

import java.time.LocalDate;
import java.time.OffsetDateTime;

public record ReviewItem(
        long id,
        String reviewType,
        String moduleCode,
        String title,
        String summary,
        String highlights,
        String problems,
        String nextActions,
        LocalDate periodStart,
        LocalDate periodEnd,
        OffsetDateTime createdAt) {
}
