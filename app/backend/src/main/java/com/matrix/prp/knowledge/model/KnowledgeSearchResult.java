package com.matrix.prp.knowledge.model;

public record KnowledgeSearchResult(
        String path,
        String name,
        String snippet,
        int score) {
}
