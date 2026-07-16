package com.matrix.prp.records.model;

import java.time.LocalDate;

public record RecordFilter(
        String moduleCode,
        Long tagId,
        LocalDate recordDate,
        String keyword) {
}
