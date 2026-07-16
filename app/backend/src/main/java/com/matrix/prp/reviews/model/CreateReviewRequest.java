package com.matrix.prp.reviews.model;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import java.time.LocalDate;

public record CreateReviewRequest(
        @Pattern(regexp = "weekly|monthly|module", message = "must be one of: weekly, monthly, module")
        @NotBlank String reviewType,
        @NotBlank String moduleCode,
        @NotBlank String title,
        String summary,
        String highlights,
        String problems,
        String nextActions,
        LocalDate periodStart,
        LocalDate periodEnd) {

    @AssertTrue(message = "periodStart must be on or before periodEnd")
    public boolean isPeriodRangeValid() {
        return periodStart == null || periodEnd == null || !periodStart.isAfter(periodEnd);
    }
}
