package com.matrix.prp.knowledge.model;

public record KnowledgeStats(
        int fileCount,
        int directoryCount,
        long totalBytes) {
}
