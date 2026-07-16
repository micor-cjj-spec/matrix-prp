package com.matrix.prp.tags.model;

import java.time.OffsetDateTime;

public record TagItem(
        long id,
        String name,
        String color,
        String description,
        OffsetDateTime createdAt) {
}
