package com.matrix.prp.mcp;

import com.matrix.prp.reviews.model.ReviewFilter;
import com.matrix.prp.reviews.model.ReviewItem;
import com.matrix.prp.reviews.service.ReviewService;
import com.matrix.prp.video.VideoDtos.Folder;
import com.matrix.prp.video.VideoDtos.Video;
import com.matrix.prp.video.VideoLibraryService;
import java.time.LocalDate;
import java.util.List;
import java.util.Objects;

/**
 * Review-only candidate for the next MCP read tool batch (Issue #218).
 *
 * This adapter deliberately has no Spring/MCP annotations and is NOT included in
 * McpToolConfiguration's registry. The separate OAuth/scope integration must be
 * reviewed before a client can enumerate or invoke these operations.
 *
 * Both existing services enforce ownership through CurrentUser.id() in their
 * repositories. This class accepts no owner ID or playback token.
 */
public final class McpReviewVideoReadAdapter {
    static final int MAX_REVIEWS = 20;
    static final int MAX_FOLDERS = 50;
    static final int MAX_VIDEOS = 30;

    private final ReviewService reviews;
    private final VideoLibraryService video;

    public McpReviewVideoReadAdapter(ReviewService reviews, VideoLibraryService video) {
        this.reviews = Objects.requireNonNull(reviews);
        this.video = Objects.requireNonNull(video);
    }

    /** Returns only a bounded projection; never returns highlight/problem/action bodies. */
    public List<ReviewPreview> listReviewPreviews(
            String reviewType, String moduleCode, LocalDate periodStart,
            LocalDate periodEnd, Integer limit) {
        int size = validateLimit(limit, MAX_REVIEWS, 10);
        String type = optionalFilter(reviewType, "reviewType");
        String module = optionalFilter(moduleCode, "moduleCode");
        if (periodStart != null && periodEnd != null && periodStart.isAfter(periodEnd)) {
            throw new IllegalArgumentException("periodStart must not be after periodEnd");
        }
        // The repository filters CurrentUser.id() and applies an SQL-side LIMIT.
        return reviews.listLimited(new ReviewFilter(type, module, periodStart, periodEnd), size)
            .stream().limit(size)
            .map(McpReviewVideoReadAdapter::preview)
            .toList();
    }

    /** Folder names and IDs only, never storage paths or upload session data. */
    public List<FolderPreview> listFolderPreviews(Integer limit) {
        int size = validateLimit(limit, MAX_FOLDERS, 20);
        return video.foldersLimited(size).stream().limit(size)
            .map(folder -> new FolderPreview(
                folder.id(), folder.parentId(), clipped(folder.name(), 120)))
            .toList();
    }

    /** Progress is informational; no playback URL, signed ticket or media bytes. */
    public List<VideoPreview> listVideoPreviews(Long folderId, Integer limit) {
        int size = validateLimit(limit, MAX_VIDEOS, 20);
        if (folderId != null && folderId <= 0) {
            throw new IllegalArgumentException("folderId must be positive");
        }
        // VideoLibraryService verifies folder ownership and filters user_id.
        return video.videosLimited(folderId, size).stream().limit(size)
            .map(item -> new VideoPreview(item.id(), item.folderId(),
                clipped(item.title(), 160),
                item.positionSeconds(), item.durationSeconds()))
            .toList();
    }

    private static ReviewPreview preview(ReviewItem item) {
        return new ReviewPreview(item.id(), item.reviewType(), item.moduleCode(),
            clipped(item.title(), 120), clipped(item.summary(), 200),
            item.periodStart(), item.periodEnd());
    }

    private static String optionalFilter(String value, String name) {
        if (value == null) return null;
        if (value.length() > 64 || value.codePoints().anyMatch(Character::isISOControl)) {
            throw new IllegalArgumentException("Invalid " + name);
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }

    private static int validateLimit(Integer requested, int maximum, int defaultValue) {
        if (requested == null) return defaultValue;
        if (requested < 1 || requested > maximum) {
            throw new IllegalArgumentException("Limit must be between 1 and " + maximum);
        }
        return requested;
    }

    private static String clipped(String value, int maxCodePoints) {
        if (value == null) return "";
        String normalized = value.replaceAll("\\s+", " ").trim();
        if (normalized.codePointCount(0, normalized.length()) <= maxCodePoints) {
            return normalized;
        }
        int end = normalized.offsetByCodePoints(0, maxCodePoints);
        return normalized.substring(0, end) + "\u2026";
    }

    public record ReviewPreview(long id, String reviewType, String moduleCode,
                                String title, String summaryExcerpt,
                                LocalDate periodStart, LocalDate periodEnd) { }

    public record FolderPreview(long id, Long parentId, String name) { }

    public record VideoPreview(long id, Long folderId, String title,
                               double positionSeconds, double durationSeconds) { }
}
