package com.matrix.prp.tags.model;

import jakarta.validation.constraints.NotBlank;

public record CreateTagRequest(
        @NotBlank String name,
        String color,
        String description) {
}
