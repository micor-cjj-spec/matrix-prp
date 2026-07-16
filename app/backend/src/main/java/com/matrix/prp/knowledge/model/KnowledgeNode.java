package com.matrix.prp.knowledge.model;

import java.util.List;

public record KnowledgeNode(
        String name,
        String path,
        String type,
        List<KnowledgeNode> children) {
}
