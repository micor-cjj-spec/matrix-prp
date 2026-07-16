package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.matrix.prp.knowledge.service.KnowledgeService;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class KnowledgeServiceTests {

    @TempDir
    private Path tempDir;

    @Test
    void buildsTreeReadsMarkdownAndSearchesVisibleFiles() throws Exception {
        Path knowledgeRoot = tempDir.resolve("knowledge");
        Files.createDirectories(knowledgeRoot.resolve("finance"));
        Files.writeString(knowledgeRoot.resolve("overview.md"), "# Overview\n\nMatrix PRP overview.");
        Files.writeString(knowledgeRoot.resolve("finance").resolve("budget.md"), "# Budget\n\nBudget budget planning notes.");
        Files.writeString(knowledgeRoot.resolve(".secret.md"), "hidden budget");
        Files.writeString(knowledgeRoot.resolve("plain.txt"), "plain budget");

        KnowledgeService service = new KnowledgeService(knowledgeRoot.toString());

        var tree = service.tree();
        assertThat(tree).extracting("name").containsExactly("finance", "overview.md");
        assertThat(tree.get(0).type()).isEqualTo("directory");
        assertThat(tree.get(0).children()).extracting("path").containsExactly("finance/budget.md");

        var file = service.readFile("finance/budget.md");
        assertThat(file.name()).isEqualTo("budget.md");
        assertThat(file.content()).contains("Budget budget planning notes.");

        var results = service.search("budget");
        assertThat(results).hasSize(1);
        assertThat(results.get(0).path()).isEqualTo("finance/budget.md");
        assertThat(results.get(0).score()).isGreaterThanOrEqualTo(12);
        assertThat(results.get(0).snippet()).contains("Budget budget planning");

        var stats = service.stats();
        assertThat(stats.fileCount()).isEqualTo(2);
        assertThat(stats.directoryCount()).isEqualTo(1);
        assertThat(stats.totalBytes()).isGreaterThan(0);
    }

    @Test
    void rejectsPathEscapeAndNonMarkdownFiles() throws Exception {
        Path knowledgeRoot = tempDir.resolve("knowledge");
        Files.createDirectories(knowledgeRoot);
        Files.writeString(tempDir.resolve("outside.md"), "outside");
        Files.writeString(knowledgeRoot.resolve("plain.txt"), "plain");

        KnowledgeService service = new KnowledgeService(knowledgeRoot.toString());

        assertThatThrownBy(() -> service.readFile("../outside.md"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Path escapes knowledge root");
        assertThatThrownBy(() -> service.readFile("plain.txt"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Knowledge file is not readable");
    }
}
