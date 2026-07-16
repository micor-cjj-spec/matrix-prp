package com.matrix.prp.modules.model;

public record ModuleItem(
        String code,
        String name,
        String description,
        String type,
        int sortOrder,
        boolean enabled) {
}
