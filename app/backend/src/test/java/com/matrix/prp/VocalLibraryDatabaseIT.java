package com.matrix.prp;

import static org.assertj.core.api.Assertions.*;

import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.vocal.VocalLibraryService;
import com.matrix.prp.vocal.VocalService;
import java.sql.PreparedStatement;
import java.sql.Statement;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.web.server.ResponseStatusException;

@SpringBootTest
@ActiveProfiles("video-integration")
class VocalLibraryDatabaseIT {
    @Autowired JdbcTemplate jdbc;
    @Autowired VocalLibraryService library;
    @Autowired VocalService vocal;
    private final List<Long> users = new ArrayList<>();

    private long createUser() {
        String username = "vocal_it_" + UUID.randomUUID().toString().replace("-", "").substring(0, 20);
        GeneratedKeyHolder key = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO prp_users(username,display_name,password_hash,is_admin,enabled) VALUES(?,?,?,0,1)",
                Statement.RETURN_GENERATED_KEYS);
            ps.setString(1, username);
            ps.setString(2, "Vocal Integration Test");
            ps.setString(3, "$2a$10$integration-only-password-hash");
            return ps;
        }, key);
        long id = key.getKey().longValue();
        users.add(id);
        return id;
    }

    private void asUser(long id) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(new UserProfile(id, "vocal_" + id, "Vocal Test"), null, List.of()));
    }

    private long createTake(long owner) {
        GeneratedKeyHolder key = new GeneratedKeyHolder();
        String analysis = "{\"voicedSamples\":0,\"medianHz\":null,\"stabilityCents\":null,"
            + "\"targetHitPercent\":null,\"guidance\":\"No pitch sample\"}";
        jdbc.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO prp_vocal_takes(user_id,exercise_code,note,duration_seconds,mime_type,storage_key,size_bytes,analysis_json) "
                + "VALUES(?,?,?,?,?,?,?,?)", Statement.RETURN_GENERATED_KEYS);
            ps.setLong(1, owner); ps.setString(2, "phrase"); ps.setString(3, ""); ps.setInt(4, 12);
            ps.setString(5, "audio/wav"); ps.setString(6, UUID.randomUUID() + ".wav");
            ps.setLong(7, 128); ps.setString(8, analysis);
            return ps;
        }, key);
        return key.getKey().longValue();
    }

    @AfterEach
    void cleanup() {
        SecurityContextHolder.clearContext();
        for (long user : users) jdbc.update("DELETE FROM prp_users WHERE id=?", user);
    }

    @Test
    void songsSectionsLessonsAssignmentsAndTakeLinksAreOwnerScopedAndPreserveRecordings() {
        long owner = createUser();
        long other = createUser();
        asUser(owner);

        var song = library.createSong(new VocalLibraryService.SongRequest(
            "可惜没如果", "林俊杰", "A", "LEARNING", "主攻曲目"));
        var section = library.createSection(song.id(), new VocalLibraryService.SectionRequest(
            "副歌第一句", "01:20", "01:42", "高音衔接与换气", 10));
        var lesson = library.createLesson(new VocalLibraryService.LessonRequest(
            LocalDate.now(), "声乐老师", "练习混声衔接", "不要强推音量"));
        var assignment = library.createAssignment(new VocalLibraryService.AssignmentRequest(
            lesson.id(), song.id(), section.id(), "副歌慢速模唱 5 次",
            "每次先听参考音，再轻声模唱", LocalDate.now().plusDays(2), "TODO"));
        long takeId = createTake(owner);
        library.attachTake(takeId, song.id(), section.id());

        assertThat(library.songs()).singleElement().satisfies(saved -> {
            assertThat(saved.title()).isEqualTo("可惜没如果");
            assertThat(saved.sectionCount()).isEqualTo(1);
        });
        assertThat(library.sections(song.id())).extracting(VocalLibraryService.Section::title)
            .containsExactly("副歌第一句");
        assertThat(library.assignments()).singleElement().satisfies(saved -> {
            assertThat(saved.lessonId()).isEqualTo(lesson.id());
            assertThat(saved.songTitle()).isEqualTo("可惜没如果");
            assertThat(saved.sectionTitle()).isEqualTo("副歌第一句");
        });
        assertThat(vocal.get(takeId).songId()).isEqualTo(song.id());
        assertThat(vocal.get(takeId).sectionTitle()).isEqualTo("副歌第一句");

        asUser(other);
        assertThat(library.songs()).isEmpty();
        assertThatThrownBy(() -> library.updateSong(song.id(),
            new VocalLibraryService.SongRequest("Cross-user edit", "", "", "LEARNING", "")))
            .isInstanceOf(ResponseStatusException.class);
        assertThatThrownBy(() -> library.createAssignment(new VocalLibraryService.AssignmentRequest(
            null, song.id(), null, "Cross-user task", "", null, "TODO")))
            .isInstanceOf(ResponseStatusException.class);
        assertThatThrownBy(() -> library.attachTake(takeId, song.id(), section.id()))
            .isInstanceOf(ResponseStatusException.class);
        assertThatThrownBy(() -> vocal.get(takeId)).isInstanceOf(ResponseStatusException.class);

        asUser(owner);
        library.deleteSection(section.id());
        assertThat(jdbc.queryForObject("SELECT section_id FROM prp_vocal_take_links WHERE take_id=?", Long.class, takeId))
            .isNull();
        assertThat(library.assignments()).singleElement().satisfies(saved -> {
            assertThat(saved.sectionId()).isNull();
            assertThat(saved.songId()).isEqualTo(song.id());
        });
        library.deleteSong(song.id());
        assertThat(vocal.get(takeId).songId()).isNull();
        assertThat(library.assignments()).singleElement().satisfies(saved -> {
            assertThat(saved.songId()).isNull();
            assertThat(saved.sectionId()).isNull();
        });
        library.deleteLesson(lesson.id());
        assertThat(library.assignments()).singleElement().satisfies(saved -> {
            assertThat(saved.lessonId()).isNull();
            assertThat(saved.status()).isEqualTo("TODO");
        });
        library.updateAssignment(assignment.id(), new VocalLibraryService.AssignmentRequest(
            null, null, null, "副歌慢速模唱 5 次", "完成一次后打勾", LocalDate.now(), "DONE"));
        assertThat(library.assignments().getFirst().status()).isEqualTo("DONE");
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM prp_vocal_takes WHERE id=? AND user_id=?",
            Integer.class, takeId, owner)).isEqualTo(1);
    }
}
