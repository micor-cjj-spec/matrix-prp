package com.matrix.prp.video;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.time.LocalDateTime;

public final class VideoDtos {
    private VideoDtos() { }

    public record Folder(long id, Long parentId, String name, int sortOrder) { }
    public record FolderRequest(Long parentId, @NotBlank @Size(max = 160) String name) { }
    public record Video(long id, Long folderId, String title, long sizeBytes,
                        LocalDateTime createdAt, double positionSeconds) { }
    public record VideoUpdate(@NotBlank @Size(max = 255) String title, Long folderId) { }
    public record UploadRequest(Long folderId, @NotBlank @Size(max = 255) String title,
                                @NotNull @Positive Long sizeBytes) { }
    public record UploadSession(String uploadId, int chunkSize, int partCount) { }
    public record UploadState(String uploadId, int chunkSize, int partCount, String state,
                              java.util.List<Integer> receivedParts) { }
    public record Playback(String url, long expiresAtEpochSeconds) { }
    public record StorageUsage(long fileCount, long bytesUsed, long quotaBytes) { }
    public record Progress(@NotNull Double positionSeconds, @NotNull Double durationSeconds) { }
}
