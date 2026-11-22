package com.matrix.prp;

import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.common.api.ResourceNotFoundException;
import com.matrix.prp.reviews.model.CreateReviewRequest;
import com.matrix.prp.reviews.model.ReviewFilter;
import com.matrix.prp.reviews.service.ReviewService;
import com.matrix.prp.video.VideoDtos.FolderRequest;
import com.matrix.prp.video.VideoDtos.Progress;
import com.matrix.prp.video.VideoLibraryService;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.web.server.ResponseStatusException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * Read-only feature acceptance against a disposable MySQL 8.4 CI database.
 * Creates only synthetic test identities and records. Does not enable MCP,
 * call production infrastructure, or connect to any actual PRP user.
 */
@SpringBootTest
@ActiveProfiles("video-integration")
@TestPropertySource(properties={
    "matrix-prp.mcp.enabled=false",
    "matrix-prp.mcp.oauth.enabled=false",
    "matrix-prp.mcp.write-enabled=false",
    "spring.ai.mcp.server.enabled=false",
    "matrix-prp.ai.spring-ai.enabled=false",
    "matrix-prp.ai.spring-ai.tools-enabled=false"
})
class ReviewVideoReadDatabaseIT {
    @Autowired ReviewService reviews;
    @Autowired VideoLibraryService videos;
    @Autowired UserStore users;
    @Autowired PasswordEncoder passwords;
    @Autowired JdbcTemplate jdbc;

    private UserAccount newOwner() {
        String username="ci_rv_"+UUID.randomUUID().toString().replace("-","").substring(0,14);
        return users.create(username,"Synthetic review/video owner",
            passwords.encode("synthetic-ci-only"),false);
    }

    private void as(UserAccount owner) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(owner.profile(),null,List.of()));
    }

    @AfterEach
    void clearIdentity() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void reviewMysqlEnforcesOwnerFilterOverlapSoftDeleteAndSqlCap() {
        UserAccount a=newOwner(),b=newOwner();
        LocalDate first=LocalDate.of(2026,11,1);
        LocalDate last=LocalDate.of(2026,11,21);
        as(a);
        for(int i=0;i<25;i++) {
            reviews.create(new CreateReviewRequest(
                "weekly","learning","A-only-"+i,"synthetic summary","","","",
                first,last));
        }
        var deleted=reviews.create(new CreateReviewRequest(
            "weekly","learning","A-deleted","synthetic","","","",first,last));
        reviews.delete(deleted.id());

        as(b);
        reviews.create(new CreateReviewRequest(
            "weekly","learning","B-only","synthetic","","","",first,last));

        var filter=new ReviewFilter("weekly","learning",first,last);
        as(a);
        var top=reviews.listLimited(filter,20);
        assertThat(top).hasSize(20);
        // The MCP-specific SQL projection must not even fetch sensitive full review fields.
        assertThat(top).allSatisfy(r -> {
            assertThat(r.title()).startsWith("A-only-");
            assertThat(r.highlights()).isNull();
            assertThat(r.problems()).isNull();
            assertThat(r.nextActions()).isNull();
        });
        assertThat(top).noneSatisfy(r -> assertThat(r.id()).isEqualTo(deleted.id()));
        assertThat(reviews.listLimited(
            new ReviewFilter("monthly","learning",first,last),20)).isEmpty();
        assertThat(reviews.listLimited(
            new ReviewFilter("weekly","learning",last.plusDays(1),null),20)).isEmpty();
        assertThat(jdbc.queryForObject(
            "SELECT COUNT(*) FROM prp_reviews WHERE user_id=? AND deleted=0",
            Integer.class,a.id())).isEqualTo(25);

        as(b);
        assertThat(reviews.listLimited(filter,20))
            .hasSize(1).extracting("title").containsExactly("B-only");
        SecurityContextHolder.clearContext();
        assertThatThrownBy(() -> reviews.listLimited(filter,10))
            .isInstanceOf(ResponseStatusException.class);
    }

    @Test
    void videoMysqlBoundsFoldersProgressAndRejectsForeignFolder() {
        UserAccount a=newOwner(),b=newOwner();
        as(a);
        var folder=videos.createFolder(new FolderRequest(null,"A Study"));
        for(int i=0;i<35;i++) {
            jdbc.update("INSERT INTO prp_video_assets " +
                "(user_id,folder_id,title,storage_key,size_bytes) VALUES (?,?,?,?,?)",
                a.id(),folder.id(),"A Lesson "+i,UUID.randomUUID().toString(),100L);
        }
        long firstVideo=jdbc.queryForObject(
            "SELECT id FROM prp_video_assets WHERE user_id=? AND folder_id=? ORDER BY id DESC LIMIT 1",
            Long.class,a.id(),folder.id());
        videos.saveProgress(firstVideo,new Progress(42.0,120.0));
        for(int i=0;i<55;i++) {
            videos.createFolder(new FolderRequest(null,"A Folder "+i));
        }
        assertThat(videos.videosLimited(folder.id(),30)).hasSize(30);
        assertThat(videos.foldersLimited(50)).hasSize(50);
        assertThat(videos.videosLimited(null,30))
            .allSatisfy(v -> assertThat(v.title()).startsWith("A Lesson"));
        var preview=videos.videosLimited(folder.id(),30);
        var saved=preview.stream().filter(v -> v.id()==firstVideo).toList();
        assertThat(saved).hasSize(1);
        assertThat(saved.get(0).positionSeconds()).isEqualTo(42.0);
        assertThat(saved.get(0).durationSeconds()).isEqualTo(120.0);

        as(b);
        var bFolder=videos.createFolder(new FolderRequest(null,"B Study"));
        jdbc.update("INSERT INTO prp_video_assets " +
            "(user_id,folder_id,title,storage_key,size_bytes) VALUES (?,?,?,?,?)",
            b.id(),bFolder.id(),"B Lesson",UUID.randomUUID().toString(),100L);
        assertThat(videos.foldersLimited(50))
            .hasSize(1).extracting("name").containsExactly("B Study");
        assertThat(videos.videosLimited(null,30))
            .hasSize(1).extracting("title").containsExactly("B Lesson");
        assertThatThrownBy(() -> videos.videosLimited(folder.id(),10))
            .isInstanceOf(ResourceNotFoundException.class);
        SecurityContextHolder.clearContext();
        assertThatThrownBy(() -> videos.foldersLimited(10))
            .isInstanceOf(ResponseStatusException.class);
    }
}
