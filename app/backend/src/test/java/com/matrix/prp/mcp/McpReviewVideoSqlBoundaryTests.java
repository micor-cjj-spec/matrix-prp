package com.matrix.prp.mcp;

import com.baomidou.mybatisplus.core.MybatisConfiguration;
import com.baomidou.mybatisplus.core.metadata.TableInfoHelper;
import org.apache.ibatis.builder.MapperBuilderAssistant;
import com.matrix.prp.reviews.entity.ReviewEntity;
import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.common.api.ResourceNotFoundException;
import com.matrix.prp.reviews.mapper.ReviewMapper;
import com.matrix.prp.reviews.model.ReviewFilter;
import com.matrix.prp.reviews.repository.MyBatisReviewRepository;
import com.matrix.prp.video.MediaTicketService;
import com.matrix.prp.video.VideoLibraryService;
import com.matrix.prp.video.VideoStorage;
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class McpReviewVideoSqlBoundaryTests {
    private ReviewMapper mapper;
    private JdbcTemplate jdbc;
    private VideoLibraryService video;
    private MediaTicketService tickets;
    private VideoStorage storage;

    @BeforeAll
    static void initializeMyBatisLambdaMapping() {
        // The production mapper registers TableInfo during MyBatis startup;
        // Mockito-only repository tests must initialize the same mapping.
        TableInfoHelper.initTableInfo(new MapperBuilderAssistant(
            new MybatisConfiguration(), "ci-synthetic-review-repository"), ReviewEntity.class);
    }

    @BeforeEach
    void setup() {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(
                new UserProfile(42, "synthetic", "Synthetic"), null, List.of()));
        mapper = mock(ReviewMapper.class);
        jdbc = mock(JdbcTemplate.class);
        tickets = mock(MediaTicketService.class);
        storage = mock(VideoStorage.class);
        video = new VideoLibraryService(jdbc, tickets, storage);
    }

    @AfterEach
    void teardown() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void boundedReviewRepositoryKeepsOwnerPredicateAndSqlLimit() {
        var repository = new MyBatisReviewRepository(mapper);
        when(mapper.selectList(any())).thenReturn(List.of());
        repository.listLimited(new ReviewFilter("weekly", "learning",
            LocalDate.of(2026, 11, 1), LocalDate.of(2026, 11, 21)), 12);
        verify(mapper).selectList(argThat(query ->
            query.getSqlSegment().contains("user_id")
                && query.getSqlSegment().contains("LIMIT 12")
                && query.getSqlSegment().contains("ORDER BY")));
        verifyNoMoreInteractions(mapper);
    }

    @Test
    void boundedReviewRepositoryRejectsInvalidLimitsBeforeQuery() {
        var repository = new MyBatisReviewRepository(mapper);
        assertThatThrownBy(() -> repository.listLimited(null, 0))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> repository.listLimited(null, 21))
            .isInstanceOf(IllegalArgumentException.class);
        verifyNoInteractions(mapper);
    }

    @Test
    void boundedVideoQueriesBindOwnerAndLimitWithoutTickets() {
        video.foldersLimited(7);
        video.videosLimited(null, 11);
        verify(jdbc).query(argThat((String sql) ->
                sql.contains("FROM prp_video_folders") && sql.contains("user_id=?")
                    && sql.contains("LIMIT ?")),
            any(RowMapper.class), eq(42L), eq(7));
        verify(jdbc).query(argThat((String sql) ->
                sql.contains("FROM prp_video_assets")
                    && sql.contains("p.user_id=a.user_id")
                    && sql.contains("a.user_id=?")
                    && sql.contains("LIMIT ?")),
            any(RowMapper.class), eq(42L), eq(11));
        verifyNoInteractions(tickets, storage);
    }

    @Test
    void foreignFolderIsRejectedBeforeReturningAnyVideoRows() {
        when(jdbc.queryForObject(
            "SELECT COUNT(*) FROM prp_video_folders WHERE id=? AND user_id=?",
            Long.class, 999L, 42L)).thenReturn(0L);
        assertThatThrownBy(() -> video.videosLimited(999L, 10))
            .isInstanceOf(ResourceNotFoundException.class);
        verify(jdbc).queryForObject(
            "SELECT COUNT(*) FROM prp_video_folders WHERE id=? AND user_id=?",
            Long.class, 999L, 42L);
        verifyNoMoreInteractions(jdbc);
        verifyNoInteractions(tickets, storage);
    }

    @Test
    void missingPrincipalFailsClosedWithoutDatabaseRead() {
        SecurityContextHolder.clearContext();
        assertThatThrownBy(() -> video.foldersLimited(7))
            .hasMessageContaining("Authentication required");
        assertThatThrownBy(() -> new MyBatisReviewRepository(mapper).listLimited(null, 7))
            .hasMessageContaining("Authentication required");
        verifyNoInteractions(jdbc, mapper, tickets, storage);
    }
}
