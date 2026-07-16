package com.matrix.prp.knowledge.api;

import com.matrix.prp.common.api.ApiResponse;
import com.matrix.prp.knowledge.model.KnowledgeFile;
import com.matrix.prp.knowledge.model.KnowledgeNode;
import com.matrix.prp.knowledge.model.KnowledgeSearchResult;
import com.matrix.prp.knowledge.model.KnowledgeStats;
import com.matrix.prp.knowledge.service.KnowledgeService;
import java.io.IOException;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/knowledge")
public class KnowledgeController {

    private final KnowledgeService knowledgeService;

    public KnowledgeController(KnowledgeService knowledgeService) {
        this.knowledgeService = knowledgeService;
    }

    @GetMapping("/tree")
    public ApiResponse<List<KnowledgeNode>> tree() throws IOException {
        return ApiResponse.success(knowledgeService.tree());
    }

    @GetMapping("/stats")
    public ApiResponse<KnowledgeStats> stats() throws IOException {
        return ApiResponse.success(knowledgeService.stats());
    }

    @GetMapping("/files")
    public ApiResponse<KnowledgeFile> file(@RequestParam String path) throws IOException {
        return ApiResponse.success(knowledgeService.readFile(path));
    }

    @GetMapping("/search")
    public ApiResponse<List<KnowledgeSearchResult>> search(@RequestParam String q) throws IOException {
        return ApiResponse.success(knowledgeService.search(q));
    }
}
