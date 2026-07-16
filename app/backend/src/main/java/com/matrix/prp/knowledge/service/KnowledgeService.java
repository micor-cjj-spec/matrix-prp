package com.matrix.prp.knowledge.service;

import com.matrix.prp.knowledge.model.KnowledgeFile;
import com.matrix.prp.knowledge.model.KnowledgeNode;
import com.matrix.prp.knowledge.model.KnowledgeSearchResult;
import com.matrix.prp.knowledge.model.KnowledgeStats;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class KnowledgeService {

    private final Path root;

    public KnowledgeService(@Value("${matrix-prp.knowledge.root:../../knowledge}") String rootPath) {
        this.root = Path.of(rootPath).toAbsolutePath().normalize();
    }

    public List<KnowledgeNode> tree() throws IOException {
        if (!Files.exists(root)) {
            return List.of();
        }
        try (Stream<Path> stream = Files.list(root)) {
            return stream
                    .filter(this::isVisibleKnowledgePath)
                    .sorted(this::comparePath)
                    .map(this::toNode)
                    .toList();
        }
    }

    public KnowledgeFile readFile(String relativePath) throws IOException {
        Path file = resolveInsideRoot(relativePath);
        if (!Files.isRegularFile(file) || !file.getFileName().toString().endsWith(".md")) {
            throw new IllegalArgumentException("Knowledge file is not readable: " + relativePath);
        }
        return new KnowledgeFile(
                toRelativePath(file),
                file.getFileName().toString(),
                Files.readString(file, StandardCharsets.UTF_8));
    }

    public List<KnowledgeSearchResult> search(String query) throws IOException {
        String normalizedQuery = query == null ? "" : query.trim();
        if (normalizedQuery.isEmpty() || !Files.exists(root)) {
            return List.of();
        }

        String lowerQuery = normalizedQuery.toLowerCase(Locale.ROOT);
        List<KnowledgeSearchResult> results = new ArrayList<>();
        try (Stream<Path> stream = Files.walk(root)) {
            for (Path file : stream
                    .filter(Files::isRegularFile)
                    .filter(this::isVisibleKnowledgePath)
                    .sorted(this::comparePath)
                    .toList()) {
                String name = file.getFileName().toString();
                String content = Files.readString(file, StandardCharsets.UTF_8);
                String lowerName = name.toLowerCase(Locale.ROOT);
                String lowerContent = content.toLowerCase(Locale.ROOT);
                int nameIndex = lowerName.indexOf(lowerQuery);
                int contentIndex = lowerContent.indexOf(lowerQuery);
                if (nameIndex < 0 && contentIndex < 0) {
                    continue;
                }
                int score = (nameIndex >= 0 ? 10 : 0) + countOccurrences(lowerContent, lowerQuery);
                results.add(new KnowledgeSearchResult(
                        toRelativePath(file),
                        name,
                        snippet(content, contentIndex >= 0 ? contentIndex : 0),
                        score));
            }
        }

        return results.stream()
                .sorted(Comparator.comparing(KnowledgeSearchResult::score).reversed()
                        .thenComparing(KnowledgeSearchResult::path))
                .limit(20)
                .toList();
    }

    public KnowledgeStats stats() throws IOException {
        if (!Files.exists(root)) {
            return new KnowledgeStats(0, 0, 0);
        }

        int fileCount = 0;
        int directoryCount = 0;
        long totalBytes = 0;
        try (Stream<Path> stream = Files.walk(root)) {
            for (Path path : stream
                    .filter(path -> !path.equals(root))
                    .filter(this::isVisibleKnowledgePath)
                    .toList()) {
                if (Files.isDirectory(path)) {
                    directoryCount++;
                } else if (Files.isRegularFile(path)) {
                    fileCount++;
                    totalBytes += Files.size(path);
                }
            }
        }
        return new KnowledgeStats(fileCount, directoryCount, totalBytes);
    }

    private KnowledgeNode toNode(Path path) {
        String type = Files.isDirectory(path) ? "directory" : "file";
        List<KnowledgeNode> children = List.of();
        if (Files.isDirectory(path)) {
            try (Stream<Path> stream = Files.list(path)) {
                children = stream
                        .filter(this::isVisibleKnowledgePath)
                        .sorted(this::comparePath)
                        .map(this::toNode)
                        .toList();
            } catch (IOException ignored) {
                children = List.of();
            }
        }
        return new KnowledgeNode(path.getFileName().toString(), toRelativePath(path), type, children);
    }

    private Path resolveInsideRoot(String relativePath) {
        Path resolved = root.resolve(relativePath).toAbsolutePath().normalize();
        if (!resolved.startsWith(root)) {
            throw new IllegalArgumentException("Path escapes knowledge root: " + relativePath);
        }
        return resolved;
    }

    private String toRelativePath(Path path) {
        return root.relativize(path.toAbsolutePath().normalize()).toString().replace('\\', '/');
    }

    private boolean isVisibleKnowledgePath(Path path) {
        String name = path.getFileName().toString();
        if (name.startsWith(".")) {
            return false;
        }
        return Files.isDirectory(path) || name.endsWith(".md");
    }

    private int comparePath(Path left, Path right) {
        boolean leftDirectory = Files.isDirectory(left);
        boolean rightDirectory = Files.isDirectory(right);
        if (leftDirectory != rightDirectory) {
            return leftDirectory ? -1 : 1;
        }
        return Comparator.comparing((Path path) -> path.getFileName().toString()).compare(left, right);
    }

    private int countOccurrences(String content, String query) {
        int count = 0;
        int index = content.indexOf(query);
        while (index >= 0) {
            count++;
            index = content.indexOf(query, index + query.length());
        }
        return count;
    }

    private String snippet(String content, int index) {
        int start = Math.max(0, index - 60);
        int end = Math.min(content.length(), index + 120);
        return content.substring(start, end)
                .replaceAll("\\s+", " ")
                .trim();
    }
}
