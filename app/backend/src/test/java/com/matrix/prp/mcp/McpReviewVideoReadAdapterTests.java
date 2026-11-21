package com.matrix.prp.mcp;

import com.matrix.prp.reviews.model.ReviewFilter;
import com.matrix.prp.reviews.model.ReviewItem;
import com.matrix.prp.reviews.service.ReviewService;
import com.matrix.prp.video.VideoDtos.Folder;
import com.matrix.prp.video.VideoDtos.Video;
import com.matrix.prp.video.VideoLibraryService;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

class McpReviewVideoReadAdapterTests {
    private ReviewService reviews;
    private VideoLibraryService video;
    private McpReviewVideoReadAdapter adapter;

    @BeforeEach
    void setup() {
        reviews = mock(ReviewService.class);
        video = mock(VideoLibraryService.class);
        adapter = new McpReviewVideoReadAdapter(reviews, video);
    }

    @Test
    void reviewsReuseFilteredServiceAndExposeOnlyShortSummary() {
        var start = LocalDate.of(2026, 10, 1);
        var end = LocalDate.of(2026, 10, 31);
        String privateNote = "PRIVATE_HIGHLIGHTS_NOT_FOR_MCP";
        String tooLong = "A".repeat(250) + "PRIVATE_TRAILING_SUMMARY";
        when(reviews.list(any(ReviewFilter.class)))
            .thenReturn(List.of(new ReviewItem(12, "monthly", "learning",
                "  My\nReview  ", tooLong, privateNote, "PRIVATE_PROBLEM",
                "PRIVATE_ACTION", start, end, OffsetDateTime.parse("2026-11-01T00:00:00Z"))));

        var result = adapter.listReviewPreviews(" monthly ", "learning", start, end, 3);
        assertThat(result).hasSize(1);
        assertThat(result.get(0).id()).isEqualTo(12);
        assertThat(result.get(0).title()).isEqualTo("My Review");
        assertThat(result.get(0).summaryExcerpt().codePointCount(
            0, result.get(0).summaryExcerpt().length())).isLessThanOrEqualTo(201);
        assertThat(result.toString()).doesNotContain(
            "PRIVATE_TRAILING_SUMMARY", "PRIVATE_HIGHLIGHTS_NOT_FOR_MCP",
            "PRIVATE_PROBLEM", "PRIVATE_ACTION");
        var filter = ArgumentCaptor.forClass(ReviewFilter.class);
        verify(reviews).list(filter.capture());
        assertThat(filter.getValue())
            .isEqualTo(new ReviewFilter("monthly", "learning", start, end));
        verifyNoInteractions(video);
    }

    @Test
    void reviewsCapResponsesToTwentyAndRetainEmptyState() {
        var rows = new ArrayList<ReviewItem>();
        for (int i = 1; i <= 40; i++) {
            rows.add(new ReviewItem(i, "weekly", "work", "Review " + i, "",
                "", "", "", null, null, OffsetDateTime.parse("2026-11-01T00:00:00Z")));
        }
        when(reviews.list(any(ReviewFilter.class))).thenReturn(rows);
        assertThat(adapter.listReviewPreviews(null, null, null, null, 20)).hasSize(20);
        when(reviews.list(any(ReviewFilter.class))).thenReturn(List.of());
        assertThat(adapter.listReviewPreviews(null, null, null, null, null)).isEmpty();
    }

    @Test
    void reviewInvalidLimitsAndFiltersFailBeforeDatabaseService() {
        assertThatThrownBy(() -> adapter.listReviewPreviews(null, null, null, null, 21))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> adapter.listReviewPreviews(null, null, null, null, 0))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> adapter.listReviewPreviews("x".repeat(65), null, null, null, 2))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> adapter.listReviewPreviews("invalid\nvalue", null, null, null, 2))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> adapter.listReviewPreviews(null, null,
            LocalDate.of(2026, 11, 2), LocalDate.of(2026, 11, 1), 2))
            .isInstanceOf(IllegalArgumentException.class);
        verifyNoInteractions(reviews, video);
    }

    @Test
    void folderAndVideoPreviewsExcludePlaybackTicketsAndUploads() {
        when(video.folders()).thenReturn(List.of(
            new Folder(10, null, "Study", 0), new Folder(11, 10L, "Week 1", 1)));
        when(video.videos(11L)).thenReturn(List.of(
            new Video(25, 11L, "Lesson 1", 50000,
                LocalDateTime.of(2026, 11, 1, 8, 0), 95, 400)));
        var folders = adapter.listFolderPreviews(1);
        var items = adapter.listVideoPreviews(11L, 1);

        assertThat(folders).hasSize(1);
        assertThat(folders.get(0).name()).isEqualTo("Study");
        assertThat(items).hasSize(1);
        assertThat(items.get(0).positionSeconds()).isEqualTo(95);
        assertThat(items.get(0).durationSeconds()).isEqualTo(400);
        assertThat(items.toString()).doesNotContain("ticket", "storageKey", "sizeBytes");
        verify(video).folders();
        verify(video).videos(11L);
        verifyNoMoreInteractions(video);
        verifyNoInteractions(reviews);
    }

    @Test
    void videoAndFolderCapsAreStrict() {
        var folders = new ArrayList<Folder>();
        var items = new ArrayList<Video>();
        for (int i = 1; i <= 60; i++) {
            folders.add(new Folder(i, null, "Folder " + i, i));
            items.add(new Video(i, null, "Lesson " + i, 1,
                LocalDateTime.of(2026, 11, 1, 8, 0), 0, 0));
        }
        when(video.folders()).thenReturn(folders);
        when(video.videos(null)).thenReturn(items);
        assertThat(adapter.listFolderPreviews(50)).hasSize(50);
        assertThat(adapter.listVideoPreviews(null, 30)).hasSize(30);
    }

    @Test
    void invalidVideoInputsFailBeforeAccessAndNoWritesExist() {
        assertThatThrownBy(() -> adapter.listVideoPreviews(0L, 3))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> adapter.listVideoPreviews(-1L, 3))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> adapter.listVideoPreviews(1L, 31))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> adapter.listFolderPreviews(0))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> adapter.listFolderPreviews(51))
            .isInstanceOf(IllegalArgumentException.class);
        verifyNoInteractions(reviews, video);
    }
}
