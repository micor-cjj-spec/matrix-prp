package com.matrix.prp.video;

import java.io.IOException;
import java.io.OutputStream;
import java.nio.channels.SeekableByteChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.UUID;
import java.util.stream.Stream;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("!test")
public class LocalVideoStorage implements VideoStorage {
    private final Path root;

    public LocalVideoStorage(@Value("${matrix-prp.video.storage-root:./data/videos}") String storageRoot)
            throws IOException {
        this.root = Path.of(storageRoot).toAbsolutePath().normalize();
        Files.createDirectories(root.resolve("media"));
        Files.createDirectories(root.resolve("temp"));
    }

    @Override
    public void writePart(long userId, String uploadId, int partNo, byte[] bytes) throws IOException {
        Path dir = uploadFolder(userId, uploadId);
        Files.createDirectories(dir);
        Path tmp = Files.createTempFile(dir, "chunk-", ".writing");
        try {
            Files.write(tmp, bytes);
            Files.move(tmp, dir.resolve(partNo + ".part"), StandardCopyOption.REPLACE_EXISTING);
        } finally {
            Files.deleteIfExists(tmp);
        }
    }

    @Override
    public boolean hasPart(long userId, String uploadId, int partNo, long expectedLength) throws IOException {
        Path part = uploadFolder(userId, uploadId).resolve(partNo + ".part");
        return Files.isRegularFile(part) && !Files.isSymbolicLink(part) && Files.size(part) == expectedLength;
    }

    @Override
    public byte[] firstPartHeader(long userId, String uploadId) throws IOException {
        try (var input = Files.newInputStream(uploadFolder(userId, uploadId).resolve("0.part"))) {
            return input.readNBytes(8);
        }
    }

    @Override
    public void complete(long userId, String uploadId, String key, int parts, long expectedSize) throws IOException {
        Path destination = mediaFile(userId, key);
        Files.createDirectories(destination.getParent());
        Path temporary = Files.createTempFile(destination.getParent(), "assembly-", ".tmp");
        try {
            try (OutputStream out = Files.newOutputStream(temporary)) {
                for (int part = 0; part < parts; part++) {
                    Files.copy(uploadFolder(userId, uploadId).resolve(part + ".part"), out);
                }
            }
            if (Files.size(temporary) != expectedSize) {
                throw new IllegalArgumentException("Assembled media size mismatch");
            }
            Files.move(temporary, destination, StandardCopyOption.REPLACE_EXISTING);
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    @Override
    public void removeUpload(long userId, String uploadId) throws IOException {
        Path dir = uploadFolder(userId, uploadId);
        if (!Files.isDirectory(dir) || Files.isSymbolicLink(dir)) return;
        try (Stream<Path> contents = Files.list(dir)) {
            for (Path child : contents.toList()) {
                if (Files.isDirectory(child)) throw new IOException("Unexpected directory in upload");
                Files.deleteIfExists(child);
            }
        }
        Files.deleteIfExists(dir);
    }

    @Override
    public void removeMedia(long userId, String key) throws IOException {
        Files.deleteIfExists(mediaFile(userId, key));
    }

    @Override
    public boolean mediaExists(long userId, String key) {
        Path path = mediaFile(userId, key);
        return Files.isRegularFile(path) && !Files.isSymbolicLink(path);
    }

    @Override
    public long mediaSize(long userId, String key) throws IOException {
        return Files.size(mediaFile(userId, key));
    }

    @Override
    public SeekableByteChannel readMedia(long userId, String key) throws IOException {
        return Files.newByteChannel(mediaFile(userId, key), StandardOpenOption.READ);
    }

    @Override
    public String internalRedirect(long userId, String key) {
        return "/_internal_prp_video/" + userId + "/" + key + ".mp4";
    }

    private Path mediaFile(long userId, String key) {
        validate(userId, key);
        return root.resolve("media").resolve(Long.toString(userId)).resolve(key + ".mp4");
    }

    private Path uploadFolder(long userId, String uploadId) {
        validate(userId, uploadId);
        return root.resolve("temp").resolve(Long.toString(userId)).resolve(uploadId);
    }

    private void validate(long userId, String id) {
        if (userId <= 0 || id == null || !UUID.fromString(id).toString().equals(id)) {
            throw new IllegalArgumentException("Invalid storage key");
        }
    }
}
