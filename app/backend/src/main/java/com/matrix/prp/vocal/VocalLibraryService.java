package com.matrix.prp.vocal;

import com.matrix.prp.auth.security.CurrentUser;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.sql.Timestamp;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Locale;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

@Service
public class VocalLibraryService {
    public record Song(long id, String title, String artist, String originalKey, String status,
                       String note, int sectionCount, LocalDateTime createdAt, LocalDateTime updatedAt) {}
    public record SongRequest(String title, String artist, String originalKey, String status, String note) {}
    public record Section(long id, long songId, String title, String startMarker, String endMarker,
                          String focus, int sortOrder, LocalDateTime createdAt, LocalDateTime updatedAt) {}
    public record SectionRequest(String title, String startMarker, String endMarker, String focus, Integer sortOrder) {}
    public record Lesson(long id, LocalDate lessonDate, String teacherName, String summary, String feedback,
                         int assignmentCount, LocalDateTime createdAt, LocalDateTime updatedAt) {}
    public record LessonRequest(LocalDate lessonDate, String teacherName, String summary, String feedback) {}
    public record Assignment(long id, Long lessonId, Long songId, Long sectionId, String title, String detail,
                             LocalDate dueDate, String status, LocalDateTime completedAt,
                             LocalDateTime createdAt, LocalDateTime updatedAt,
                             String songTitle, String sectionTitle) {}
    public record AssignmentRequest(Long lessonId, Long songId, Long sectionId, String title, String detail,
                                    LocalDate dueDate, String status) {}

    private final JdbcTemplate jdbc;
    private final RowMapper<Song> songRow = (rs, i) -> new Song(
        rs.getLong("id"), rs.getString("title"), rs.getString("artist"), rs.getString("original_key"),
        rs.getString("status"), rs.getString("note"), rs.getInt("section_count"),
        dateTime(rs, "created_at"), dateTime(rs, "updated_at"));
    private final RowMapper<Section> sectionRow = (rs, i) -> new Section(
        rs.getLong("id"), rs.getLong("song_id"), rs.getString("title"), rs.getString("start_marker"),
        rs.getString("end_marker"), rs.getString("focus"), rs.getInt("sort_order"),
        dateTime(rs, "created_at"), dateTime(rs, "updated_at"));
    private final RowMapper<Lesson> lessonRow = (rs, i) -> new Lesson(
        rs.getLong("id"), rs.getDate("lesson_date").toLocalDate(), rs.getString("teacher_name"),
        rs.getString("summary"), rs.getString("feedback"), rs.getInt("assignment_count"),
        dateTime(rs, "created_at"), dateTime(rs, "updated_at"));
    private final RowMapper<Assignment> assignmentRow = (rs, i) -> new Assignment(
        rs.getLong("id"), nullableLong(rs, "lesson_id"), nullableLong(rs, "song_id"),
        nullableLong(rs, "section_id"), rs.getString("title"), rs.getString("detail"),
        nullableDate(rs, "due_date"), rs.getString("status"), nullableDateTime(rs, "completed_at"),
        dateTime(rs, "created_at"), dateTime(rs, "updated_at"),
        rs.getString("song_title"), rs.getString("section_title"));

    public VocalLibraryService(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    public List<Song> songs() {
        long user = CurrentUser.id();
        return jdbc.query("SELECT s.id,s.title,s.artist,s.original_key,s.status,s.note,"
            + "(SELECT COUNT(*) FROM prp_vocal_song_sections sec WHERE sec.song_id=s.id AND sec.user_id=s.user_id) section_count,"
            + "s.created_at,s.updated_at FROM prp_vocal_songs s WHERE s.user_id=? "
            + "ORDER BY s.updated_at DESC,s.id DESC", songRow, user);
    }

    @Transactional
    public Song createSong(SongRequest request) {
        long user = CurrentUser.id();
        SongFields fields = songFields(request);
        GeneratedKeyHolder key = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO prp_vocal_songs(user_id,title,artist,original_key,status,note) VALUES(?,?,?,?,?,?)",
                Statement.RETURN_GENERATED_KEYS);
            ps.setLong(1, user); ps.setString(2, fields.title()); ps.setString(3, fields.artist());
            ps.setString(4, fields.originalKey()); ps.setString(5, fields.status()); ps.setString(6, fields.note());
            return ps;
        }, key);
        return song(key.getKey().longValue(), user);
    }

    @Transactional
    public Song updateSong(long id, SongRequest request) {
        long user = CurrentUser.id();
        SongFields fields = songFields(request);
        int changed = jdbc.update("UPDATE prp_vocal_songs SET title=?,artist=?,original_key=?,status=?,note=? "
            + "WHERE id=? AND user_id=?", fields.title(), fields.artist(), fields.originalKey(),
            fields.status(), fields.note(), id, user);
        requireUpdated(changed, "Song not found");
        return song(id, user);
    }

    @Transactional
    public void deleteSong(long id) {
        int changed = jdbc.update("DELETE FROM prp_vocal_songs WHERE id=? AND user_id=?", id, CurrentUser.id());
        requireUpdated(changed, "Song not found");
    }

    public List<Section> sections(long songId) {
        long user = CurrentUser.id();
        requireSong(songId, user);
        return jdbc.query("SELECT id,song_id,title,start_marker,end_marker,focus,sort_order,created_at,updated_at "
            + "FROM prp_vocal_song_sections WHERE user_id=? AND song_id=? ORDER BY sort_order,id",
            sectionRow, user, songId);
    }

    @Transactional
    public Section createSection(long songId, SectionRequest request) {
        long user = CurrentUser.id();
        requireSong(songId, user);
        SectionFields fields = sectionFields(request);
        GeneratedKeyHolder key = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO prp_vocal_song_sections(user_id,song_id,title,start_marker,end_marker,focus,sort_order) "
                + "VALUES(?,?,?,?,?,?,?)", Statement.RETURN_GENERATED_KEYS);
            ps.setLong(1, user); ps.setLong(2, songId); ps.setString(3, fields.title());
            ps.setString(4, fields.startMarker()); ps.setString(5, fields.endMarker());
            ps.setString(6, fields.focus()); ps.setInt(7, fields.sortOrder());
            return ps;
        }, key);
        return section(key.getKey().longValue(), user);
    }

    @Transactional
    public Section updateSection(long id, SectionRequest request) {
        long user = CurrentUser.id();
        SectionFields fields = sectionFields(request);
        int changed = jdbc.update("UPDATE prp_vocal_song_sections SET title=?,start_marker=?,end_marker=?,focus=?,sort_order=? "
            + "WHERE id=? AND user_id=?", fields.title(), fields.startMarker(), fields.endMarker(),
            fields.focus(), fields.sortOrder(), id, user);
        requireUpdated(changed, "Song section not found");
        return section(id, user);
    }

    @Transactional
    public void deleteSection(long id) {
        int changed = jdbc.update("DELETE FROM prp_vocal_song_sections WHERE id=? AND user_id=?", id, CurrentUser.id());
        requireUpdated(changed, "Song section not found");
    }

    public List<Lesson> lessons() {
        long user = CurrentUser.id();
        return jdbc.query("SELECT l.id,l.lesson_date,l.teacher_name,l.summary,l.feedback,"
            + "(SELECT COUNT(*) FROM prp_vocal_assignments a WHERE a.lesson_id=l.id AND a.user_id=l.user_id) assignment_count,"
            + "l.created_at,l.updated_at FROM prp_vocal_lessons l WHERE l.user_id=? "
            + "ORDER BY l.lesson_date DESC,l.id DESC LIMIT 100", lessonRow, user);
    }

    @Transactional
    public Lesson createLesson(LessonRequest request) {
        long user = CurrentUser.id();
        LessonFields fields = lessonFields(request);
        GeneratedKeyHolder key = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO prp_vocal_lessons(user_id,lesson_date,teacher_name,summary,feedback) VALUES(?,?,?,?,?)",
                Statement.RETURN_GENERATED_KEYS);
            ps.setLong(1, user); ps.setDate(2, java.sql.Date.valueOf(fields.date()));
            ps.setString(3, fields.teacher()); ps.setString(4, fields.summary()); ps.setString(5, fields.feedback());
            return ps;
        }, key);
        return lesson(key.getKey().longValue(), user);
    }

    @Transactional
    public Lesson updateLesson(long id, LessonRequest request) {
        long user = CurrentUser.id();
        LessonFields fields = lessonFields(request);
        int changed = jdbc.update("UPDATE prp_vocal_lessons SET lesson_date=?,teacher_name=?,summary=?,feedback=? "
            + "WHERE id=? AND user_id=?", fields.date(), fields.teacher(), fields.summary(), fields.feedback(), id, user);
        requireUpdated(changed, "Lesson not found");
        return lesson(id, user);
    }

    @Transactional
    public void deleteLesson(long id) {
        int changed = jdbc.update("DELETE FROM prp_vocal_lessons WHERE id=? AND user_id=?", id, CurrentUser.id());
        requireUpdated(changed, "Lesson not found");
    }

    public List<Assignment> assignments() {
        long user = CurrentUser.id();
        return jdbc.query("SELECT a.id,a.lesson_id,a.song_id,a.section_id,a.title,a.detail,a.due_date,a.status,"
            + "a.completed_at,a.created_at,a.updated_at,s.title song_title,sec.title section_title "
            + "FROM prp_vocal_assignments a "
            + "LEFT JOIN prp_vocal_songs s ON s.id=a.song_id AND s.user_id=a.user_id "
            + "LEFT JOIN prp_vocal_song_sections sec ON sec.id=a.section_id AND sec.user_id=a.user_id "
            + "WHERE a.user_id=? ORDER BY CASE WHEN a.status='DONE' THEN 1 ELSE 0 END,"
            + "a.due_date IS NULL,a.due_date,a.id DESC LIMIT 200", assignmentRow, user);
    }

    @Transactional
    public Assignment createAssignment(AssignmentRequest request) {
        long user = CurrentUser.id();
        AssignmentFields fields = assignmentFields(request, user);
        GeneratedKeyHolder key = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO prp_vocal_assignments(user_id,lesson_id,song_id,section_id,title,detail,due_date,status,completed_at) "
                + "VALUES(?,?,?,?,?,?,?,?,CASE WHEN ?='DONE' THEN CURRENT_TIMESTAMP ELSE NULL END)",
                Statement.RETURN_GENERATED_KEYS);
            ps.setLong(1,user); setLong(ps,2,fields.lessonId()); setLong(ps,3,fields.songId());
            setLong(ps,4,fields.sectionId()); ps.setString(5,fields.title()); ps.setString(6,fields.detail());
            setDate(ps,7,fields.dueDate()); ps.setString(8,fields.status()); ps.setString(9,fields.status());
            return ps;
        }, key);
        return assignment(key.getKey().longValue(), user);
    }

    @Transactional
    public Assignment updateAssignment(long id, AssignmentRequest request) {
        long user = CurrentUser.id();
        AssignmentFields fields = assignmentFields(request, user);
        int changed = jdbc.update("UPDATE prp_vocal_assignments SET lesson_id=?,song_id=?,section_id=?,title=?,detail=?,"
            + "due_date=?,status=?,completed_at=CASE WHEN ?='DONE' THEN COALESCE(completed_at,CURRENT_TIMESTAMP) ELSE NULL END "
            + "WHERE id=? AND user_id=?", fields.lessonId(), fields.songId(), fields.sectionId(), fields.title(),
            fields.detail(), fields.dueDate(), fields.status(), fields.status(), id, user);
        requireUpdated(changed, "Assignment not found");
        return assignment(id, user);
    }

    @Transactional
    public void deleteAssignment(long id) {
        int changed = jdbc.update("DELETE FROM prp_vocal_assignments WHERE id=? AND user_id=?", id, CurrentUser.id());
        requireUpdated(changed, "Assignment not found");
    }

    /**
     * Called inside the recording upload transaction. All references must belong to the
     * current owner; the legacy recording table is intentionally not altered by V24.
     */
    @Transactional
    public void attachTake(long user, long takeId, Long songId, Long sectionId) {
        if (songId == null && sectionId == null) return;
        if (songId == null && sectionId != null)
            throw badRequest("A song must be selected before a section");
        requireOwned("SELECT id FROM prp_vocal_takes WHERE id=? AND user_id=?", takeId, user, "Recording not found");
        requireSong(songId, user);
        if (sectionId != null) requireSection(sectionId, songId, user);
        jdbc.update("INSERT INTO prp_vocal_take_links(user_id,take_id,song_id,section_id) VALUES(?,?,?,?) "
            + "ON DUPLICATE KEY UPDATE song_id=VALUES(song_id),section_id=VALUES(section_id),updated_at=CURRENT_TIMESTAMP",
            user, takeId, songId, sectionId);
    }

    private Song song(long id, long user) {
        List<Song> rows = jdbc.query("SELECT s.id,s.title,s.artist,s.original_key,s.status,s.note,"
            + "(SELECT COUNT(*) FROM prp_vocal_song_sections sec WHERE sec.song_id=s.id AND sec.user_id=s.user_id) section_count,"
            + "s.created_at,s.updated_at FROM prp_vocal_songs s WHERE s.id=? AND s.user_id=?", songRow, id, user);
        if (rows.isEmpty()) throw notFound("Song not found");
        return rows.getFirst();
    }
    private Section section(long id, long user) {
        List<Section> rows = jdbc.query("SELECT id,song_id,title,start_marker,end_marker,focus,sort_order,created_at,updated_at "
            + "FROM prp_vocal_song_sections WHERE id=? AND user_id=?", sectionRow, id, user);
        if (rows.isEmpty()) throw notFound("Song section not found");
        return rows.getFirst();
    }
    private Lesson lesson(long id, long user) {
        List<Lesson> rows = jdbc.query("SELECT l.id,l.lesson_date,l.teacher_name,l.summary,l.feedback,"
            + "(SELECT COUNT(*) FROM prp_vocal_assignments a WHERE a.lesson_id=l.id AND a.user_id=l.user_id) assignment_count,"
            + "l.created_at,l.updated_at FROM prp_vocal_lessons l WHERE l.id=? AND l.user_id=?", lessonRow, id, user);
        if (rows.isEmpty()) throw notFound("Lesson not found");
        return rows.getFirst();
    }
    private Assignment assignment(long id, long user) {
        List<Assignment> rows = jdbc.query("SELECT a.id,a.lesson_id,a.song_id,a.section_id,a.title,a.detail,a.due_date,a.status,"
            + "a.completed_at,a.created_at,a.updated_at,s.title song_title,sec.title section_title "
            + "FROM prp_vocal_assignments a "
            + "LEFT JOIN prp_vocal_songs s ON s.id=a.song_id AND s.user_id=a.user_id "
            + "LEFT JOIN prp_vocal_song_sections sec ON sec.id=a.section_id AND sec.user_id=a.user_id "
            + "WHERE a.id=? AND a.user_id=?", assignmentRow, id, user);
        if (rows.isEmpty()) throw notFound("Assignment not found");
        return rows.getFirst();
    }

    private void requireSong(Long id, long user) {
        if (id == null || jdbc.queryForList("SELECT id FROM prp_vocal_songs WHERE id=? AND user_id=?", id, user).isEmpty())
            throw notFound("Song not found");
    }
    private void requireSection(Long id, Long songId, long user) {
        if (id == null || jdbc.queryForList("SELECT id FROM prp_vocal_song_sections WHERE id=? AND song_id=? AND user_id=?",
            id, songId, user).isEmpty()) throw notFound("Song section not found");
    }
    private void requireLesson(Long id, long user) {
        if (id != null && jdbc.queryForList("SELECT id FROM prp_vocal_lessons WHERE id=? AND user_id=?", id, user).isEmpty())
            throw notFound("Lesson not found");
    }
    private void requireOwned(String sql, long id, long user, String message) {
        if (jdbc.queryForList(sql, id, user).isEmpty()) throw notFound(message);
    }

    private SongFields songFields(SongRequest r) {
        if (r == null) throw badRequest("Song request is required");
        String title = required(r.title(), 120, "Song title");
        String artist = text(r.artist(), 120, "Artist");
        String key = text(r.originalKey(), 20, "Original key");
        String status = r.status() == null || r.status().isBlank() ? "LEARNING" : r.status().trim().toUpperCase(Locale.ROOT);
        if (!List.of("PLANNED","LEARNING","MASTERED").contains(status)) throw badRequest("Invalid song status");
        return new SongFields(title, artist, key, status, text(r.note(), 500, "Song note"));
    }
    private SectionFields sectionFields(SectionRequest r) {
        if (r == null) throw badRequest("Section request is required");
        int order = r.sortOrder() == null ? 0 : r.sortOrder();
        if (order < 0 || order > 9999) throw badRequest("Invalid section order");
        return new SectionFields(required(r.title(),120,"Section title"), text(r.startMarker(),40,"Start marker"),
            text(r.endMarker(),40,"End marker"), text(r.focus(),500,"Section focus"), order);
    }
    private LessonFields lessonFields(LessonRequest r) {
        if (r == null || r.lessonDate() == null) throw badRequest("Lesson date is required");
        return new LessonFields(r.lessonDate(), text(r.teacherName(),120,"Teacher name"),
            text(r.summary(),4000,"Lesson summary"), text(r.feedback(),4000,"Teacher feedback"));
    }
    private AssignmentFields assignmentFields(AssignmentRequest r, long user) {
        if (r == null) throw badRequest("Assignment request is required");
        String title = required(r.title(),160,"Assignment title");
        String detail = text(r.detail(),4000,"Assignment detail");
        String status = r.status() == null || r.status().isBlank() ? "TODO" : r.status().trim().toUpperCase(Locale.ROOT);
        if (!List.of("TODO","IN_PROGRESS","DONE").contains(status)) throw badRequest("Invalid assignment status");
        requireLesson(r.lessonId(), user);
        if (r.songId() != null) requireSong(r.songId(), user);
        if (r.sectionId() != null) {
            if (r.songId() == null) throw badRequest("A song must be selected before a section");
            requireSection(r.sectionId(), r.songId(), user);
        }
        return new AssignmentFields(r.lessonId(), r.songId(), r.sectionId(), title, detail, r.dueDate(), status);
    }

    private static String required(String value, int max, String field) {
        String clean = value == null ? "" : value.trim();
        if (clean.isEmpty() || clean.length() > max) throw badRequest(field + " is required and must be at most " + max + " characters");
        return clean;
    }
    private static String text(String value, int max, String field) {
        String clean = value == null ? "" : value.trim();
        if (clean.length() > max) throw badRequest(field + " must be at most " + max + " characters");
        return clean;
    }
    private static void requireUpdated(int count, String message) { if (count == 0) throw notFound(message); }
    private static ResponseStatusException badRequest(String message) { return new ResponseStatusException(HttpStatus.BAD_REQUEST, message); }
    private static ResponseStatusException notFound(String message) { return new ResponseStatusException(HttpStatus.NOT_FOUND, message); }
    private static LocalDateTime dateTime(ResultSet rs, String name) throws SQLException { return rs.getTimestamp(name).toLocalDateTime(); }
    private static LocalDateTime nullableDateTime(ResultSet rs, String name) throws SQLException {
        Timestamp value = rs.getTimestamp(name); return value == null ? null : value.toLocalDateTime();
    }
    private static Long nullableLong(ResultSet rs, String name) throws SQLException {
        Object value = rs.getObject(name); return value == null ? null : ((Number)value).longValue();
    }
    private static LocalDate nullableDate(ResultSet rs, String name) throws SQLException {
        java.sql.Date value = rs.getDate(name); return value == null ? null : value.toLocalDate();
    }
    private static void setLong(PreparedStatement ps, int index, Long value) throws SQLException {
        if (value == null) ps.setNull(index, java.sql.Types.BIGINT); else ps.setLong(index, value);
    }
    private static void setDate(PreparedStatement ps, int index, LocalDate value) throws SQLException {
        if (value == null) ps.setNull(index, java.sql.Types.DATE); else ps.setDate(index, java.sql.Date.valueOf(value));
    }

    private record SongFields(String title, String artist, String originalKey, String status, String note) {}
    private record SectionFields(String title, String startMarker, String endMarker, String focus, int sortOrder) {}
    private record LessonFields(LocalDate date, String teacher, String summary, String feedback) {}
    private record AssignmentFields(Long lessonId, Long songId, Long sectionId, String title, String detail,
                                    LocalDate dueDate, String status) {}
}
