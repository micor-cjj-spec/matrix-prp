package com.matrix.prp.reviews.model;

import java.time.LocalDate;

public record ReviewFilter(
        String reviewType,
        String moduleCode,
        LocalDate periodStart,
        LocalDate periodEnd) {
}
