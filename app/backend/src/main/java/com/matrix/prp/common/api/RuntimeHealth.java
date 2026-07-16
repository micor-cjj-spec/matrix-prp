package com.matrix.prp.common.api;

import java.util.List;

public record RuntimeHealth(
        String status,
        String persistence,
        String database,
        String knowledgeRoot,
        boolean knowledgeAvailable,
        List<String> activeProfiles) {
}
