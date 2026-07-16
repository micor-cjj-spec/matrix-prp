package com.matrix.prp.records.model;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;

public record RecordItem(
        long id,
        String moduleCode,
        String title,
        String content,
        LocalDate recordDate,
        OffsetDateTime createdAt,
        List<RecordTagItem> tags) {
}
