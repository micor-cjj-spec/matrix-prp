package com.matrix.prp.dashboard.model;

public record DashboardModule(
        String code,
        String name,
        String description,
        boolean enabled) {
}
