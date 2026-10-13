package com.matrix.prp.video;

import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.common.api.ResourceNotFoundException;
import com.matrix.prp.video.VideoDtos.*;
import java.io.IOException;
import java.sql.PreparedStatement;
import java.sql.Statement;
import java.time.LocalDateTime;
import java.util.List;
import java.util.ArrayList;
import java.util.UUID;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.server.ResponseStatusException;

@Service
@Profile("!test")
public class VideoLibraryService {
    public static final int CHUNK_SIZE = 8 * 1024 * 1024;
    private static final long MAX_FILE_SIZE = 2L * 1024 * 1024 * 1024;
    private static final long MAX_USER_STORAGE = 20L * 1024 * 1024 * 1024;

    private static final Logger log = LoggerFactory.getLogger(VideoLibraryService.class);
    private final JdbcTemplate jdbc;
    private final MediaTicketService tickets;
    private final VideoStorage storage;
    private final RowMapper<Folder> folderRow = (rs, i) -> new Folder(rs.getLong("id"),
            rs.getObject("parent_id", Long.class), rs.getString("name"), rs.getInt("sort_order"));
    private final RowMapper<Video> videoRow = (rs, i) -> new Video(rs.getLong("id"),
            rs.getObject("folder_id", Long.class), rs.getString("title"), rs.getLong("size_bytes"),
            rs.getTimestamp("created_at").toLocalDateTime(), rs.getDouble("position_seconds"),
            rs.getDouble("duration_seconds"));

    public VideoLibraryService(JdbcTemplate jdbc, MediaTicketService tickets, VideoStorage storage) {
        this.jdbc = jdbc;
        this.tickets = tickets;
        this.storage = storage;
    }

    public List<Folder> folders() {
        return jdbc.query("SELECT id,parent_id,name,sort_order FROM prp_video_folders " +
                "WHERE user_id=? ORDER BY sort_order,id", folderRow, CurrentUser.id());
    }

    public Folder createFolder(FolderRequest request) {
        long user = CurrentUser.id();
        requireFolder(user, request.parentId());
        GeneratedKeyHolder holder = new GeneratedKeyHolder();
        jdbc.update(conn -> {
            PreparedStatement ps = conn.prepareStatement(
                    "INSERT INTO prp_video_folders (user_id,parent_id,name,sort_order) VALUES (?,?,?,0)",
                    Statement.RETURN_GENERATED_KEYS);
            ps.setLong(1, user);
            if (request.parentId() == null) ps.setNull(2, java.sql.Types.BIGINT);
            else ps.setLong(2, request.parentId());
            ps.setString(3, request.name().trim());
            return ps;
        }, holder);
        return new Folder(holder.getKey().longValue(), request.parentId(), request.name().trim(), 0);
    }

    public Folder renameFolder(long id, String name) {
        long user = CurrentUser.id();
        if (name == null || name.isBlank() || name.length() > 160) throw new IllegalArgumentException("Invalid name");
        int updated = jdbc.update("UPDATE prp_video_folders SET name=? WHERE id=? AND user_id=?",
                name.trim(), id, user);
        if (updated == 0) throw new ResourceNotFoundException("Folder not found");
        return jdbc.query("SELECT id,parent_id,name,sort_order FROM prp_video_folders " +
                "WHERE id=? AND user_id=?", folderRow, id, user).get(0);
    }

    @Transactional
    public void deleteFolder(long id) {
        long user = CurrentUser.id();
        requireFolder(user, id);
        Long childCount = jdbc.queryForObject(
                "SELECT COUNT(*) FROM prp_video_folders WHERE user_id=? AND parent_id=?", Long.class, user, id);
        Long videoCount = jdbc.queryForObject(
                "SELECT COUNT(*) FROM prp_video_assets WHERE user_id=? AND folder_id=?", Long.class, user, id);
        if (childCount > 0 || videoCount > 0) throw new IllegalArgumentException("Folder is not empty");
        jdbc.update("DELETE FROM prp_video_folders WHERE user_id=? AND id=?", user, id);
    }

    public List<Video> videos(Long folderId) {
        long user = CurrentUser.id();
        if (folderId != null) requireFolder(user, folderId);
        String query = "SELECT a.id,a.folder_id,a.title,a.size_bytes,a.created_at, " +
                "COALESCE(p.position_seconds,0) AS position_seconds, " +
                "COALESCE(p.duration_seconds,0) AS duration_seconds FROM prp_video_assets a " +
                "LEFT JOIN prp_video_progress p ON p.video_id=a.id AND p.user_id=a.user_id " +
                "WHERE a.user_id=?" + (folderId == null ? "" : " AND a.folder_id=?") +
                " ORDER BY a.created_at DESC,a.id DESC";
        return folderId == null ? jdbc.query(query, videoRow, user) : jdbc.query(query, videoRow, user, folderId);
    }

    public Video updateVideo(long id, VideoUpdate request) {
        long user = CurrentUser.id();
        requireVideo(user, id);
        requireFolder(user, request.folderId());
        int count = jdbc.update(
                "UPDATE prp_video_assets SET title=?,folder_id=? WHERE id=? AND user_id=?",
                request.title().trim(), request.folderId(), id, user);
        if (count != 1) throw new ResourceNotFoundException("Video not found");
        return findVideo(user, id);
    }

    @Transactional
    public void deleteVideo(long id) throws IOException {
        long user = CurrentUser.id();
        Asset asset = requireVideo(user, id);
        jdbc.update("DELETE FROM prp_video_assets WHERE id=? AND user_id=?", id, user);
        afterCommit(() -> storage.removeMedia(user, asset.storageKey()));
    }

    public Video saveProgress(long id, Progress request) {
        long user = CurrentUser.id();
        requireVideo(user, id);
        double position = request.positionSeconds();
        double duration = request.durationSeconds();
        if (!Double.isFinite(position) || !Double.isFinite(duration) || position < 0
                || duration < 0 || position > 1.0e8 || duration > 1.0e8) {
            throw new IllegalArgumentException("Invalid playback position");
        }
        jdbc.update("INSERT INTO prp_video_progress (user_id,video_id,position_seconds,duration_seconds) " +
                "VALUES (?,?,?,?) ON DUPLICATE KEY UPDATE position_seconds=VALUES(position_seconds), " +
                "duration_seconds=VALUES(duration_seconds), updated_at=CURRENT_TIMESTAMP(6)",
                user, id, position, duration);
        return findVideo(user, id);
    }

    public Playback playback(long id) {
        long user = CurrentUser.id();
        requireVideo(user, id);
        var ticket = tickets.issue(id, user);
        return new Playback("/api/video/media/" + id + "?ticket=" + ticket.value(), ticket.expiresAtEpochSeconds());
    }

    public MediaHandle authorizedMedia(long id, String token) {
        long user = tickets.verify(token, id);
        Asset asset = requireVideo(user, id);
        if (!storage.mediaExists(user, asset.storageKey())) {
            throw new ResourceNotFoundException("Video file is missing");
        }
        return new MediaHandle(user, asset.storageKey());
    }

    public record MediaHandle(long userId, String key) { }

    public StorageUsage usage() {
        long user = CurrentUser.id();
        return jdbc.queryForObject(
                "SELECT COUNT(*) AS file_count,COALESCE(SUM(size_bytes),0) AS bytes_used " +
                "FROM prp_video_assets WHERE user_id=?",
                (rs, row) -> new StorageUsage(rs.getLong("file_count"), rs.getLong("bytes_used"),
                        MAX_USER_STORAGE), user);
    }

    public UploadSession beginUpload(UploadRequest request) {
        long user = CurrentUser.id();
        requireFolder(user, request.folderId());
        long size = request.sizeBytes();
        if (size > MAX_FILE_SIZE) throw new ResponseStatusException(HttpStatus.valueOf(413), "Video exceeds 2 GiB");
        Long used = jdbc.queryForObject("SELECT COALESCE(SUM(size_bytes),0) FROM prp_video_assets WHERE user_id=?",
                Long.class, user);
        Long reserved = jdbc.queryForObject(
                "SELECT COALESCE(SUM(size_bytes),0) FROM prp_video_uploads " +
                "WHERE user_id=? AND state='UPLOADING' AND expires_at>CURRENT_TIMESTAMP(6)",
                Long.class, user);
        if (used + reserved + size > MAX_USER_STORAGE) {
            throw new ResponseStatusException(HttpStatus.valueOf(413), "Storage quota exceeded");
        }
        int parts = (int) ((size + CHUNK_SIZE - 1) / CHUNK_SIZE);
        String id = UUID.randomUUID().toString();
        jdbc.update("INSERT INTO prp_video_uploads (id,user_id,folder_id,title,size_bytes,part_count,state,expires_at) " +
                        "VALUES (?,?,?,?,?,?,'UPLOADING',?)",
                id, user, request.folderId(), request.title().trim(), size, parts, LocalDateTime.now().plusHours(24));
        return new UploadSession(id, CHUNK_SIZE, parts);
    }

    public UploadState uploadStatus(String id) throws IOException {
        long user = CurrentUser.id();
        Upload upload = ownedUpload(id, user);
        if (!"COMPLETE".equals(upload.state)) requireActive(upload);
        List<Integer> received = new ArrayList<>();
        if ("UPLOADING".equals(upload.state)) {
            for (int number = 0; number < upload.partCount; number++) {
                long expected = number == upload.partCount - 1
                        ? upload.sizeBytes - (long) number * CHUNK_SIZE : CHUNK_SIZE;
                if (storage.hasPart(user, id, number, expected)) received.add(number);
            }
        }
        return new UploadState(id, CHUNK_SIZE, upload.partCount, upload.state, List.copyOf(received));
    }

    public void writeChunk(String id, int number, byte[] contents) throws IOException {
        long user = CurrentUser.id();
        Upload upload = ownedUpload(id, user);
        requireActive(upload);
        if (number < 0 || number >= upload.partCount) throw new IllegalArgumentException("Invalid part number");
        long expected = number == upload.partCount - 1
                ? upload.sizeBytes - (long) number * CHUNK_SIZE : CHUNK_SIZE;
        if (contents.length != expected) throw new IllegalArgumentException("Incorrect chunk length");
        storage.writePart(user, id, number, contents);
    }

    @Transactional
    public synchronized Video completeUpload(String id) throws IOException {
        long user = CurrentUser.id();
        Upload upload = ownedUpload(id, user);
        if ("COMPLETE".equals(upload.state) && upload.assetId != null) {
            return findVideo(user, upload.assetId);
        }
        requireActive(upload);
        for (int i = 0; i < upload.partCount; i++) {
            long expected = i == upload.partCount - 1
                    ? upload.sizeBytes - (long) i * CHUNK_SIZE : CHUNK_SIZE;
            if (!storage.hasPart(user, id, i, expected)) {
                throw new IllegalArgumentException("Missing or invalid upload part: " + i);
            }
        }
        byte[] header = storage.firstPartHeader(user, id);
        if (header.length != 8 || header[4] != 'f' || header[5] != 't'
                || header[6] != 'y' || header[7] != 'p') {
            throw new IllegalArgumentException("Only MP4 video is supported");
        }
        String storageKey = UUID.randomUUID().toString();
        storage.complete(user, id, storageKey, upload.partCount, upload.sizeBytes);
        try {
            GeneratedKeyHolder holder = new GeneratedKeyHolder();
            jdbc.update(conn -> {
                PreparedStatement ps = conn.prepareStatement(
                        "INSERT INTO prp_video_assets (user_id,folder_id,title,storage_key,size_bytes) " +
                                "VALUES (?,?,?,?,?)", Statement.RETURN_GENERATED_KEYS);
                ps.setLong(1, user);
                if (upload.folderId == null) ps.setNull(2, java.sql.Types.BIGINT);
                else ps.setLong(2, upload.folderId);
                ps.setString(3, upload.title);
                ps.setString(4, storageKey);
                ps.setLong(5, upload.sizeBytes);
                return ps;
            }, holder);
            long assetId = holder.getKey().longValue();
            int transitioned = jdbc.update(
                    "UPDATE prp_video_uploads SET state='COMPLETE',asset_id=? " +
                    "WHERE id=? AND user_id=? AND state='UPLOADING' " +
                    "AND expires_at>CURRENT_TIMESTAMP(6)", assetId, id, user);
            if (transitioned != 1) {
                throw new IllegalStateException("Upload expired while being assembled");
            }
            Video saved = findVideo(user, assetId);
            afterCommit(() -> storage.removeUpload(user, id));
            return saved;
        } catch (Exception exception) {
            // The database transaction may roll back; the completed file is then orphaned.
            // Keep it inaccessible and let a separate orphan-media sweep clean it later.
            log.error("Video metadata persistence failed after assembling storage key {}", storageKey, exception);
            throw exception;
        }
    }

    private Video findVideo(long user, long id) {
        return jdbc.query("SELECT a.id,a.folder_id,a.title,a.size_bytes,a.created_at, " +
                "COALESCE(p.position_seconds,0) AS position_seconds, " +
                "COALESCE(p.duration_seconds,0) AS duration_seconds FROM prp_video_assets a " +
                "LEFT JOIN prp_video_progress p ON p.video_id=a.id AND p.user_id=a.user_id " +
                "WHERE a.user_id=? AND a.id=?", videoRow, user, id)
                .stream().findFirst().orElseThrow(() -> new ResourceNotFoundException("Video not found"));
    }

    private void requireFolder(long user, Long folderId) {
        if (folderId == null) return;
        Long found = jdbc.queryForObject("SELECT COUNT(*) FROM prp_video_folders WHERE id=? AND user_id=?",
                Long.class, folderId, user);
        if (found == 0) throw new ResourceNotFoundException("Folder not found");
    }

    private Asset requireVideo(long user, long id) {
        return jdbc.query("SELECT storage_key,size_bytes FROM prp_video_assets " +
                "WHERE id=? AND user_id=?", (rs, i) -> new Asset(rs.getString(1), rs.getLong(2)), id, user)
                .stream().findFirst().orElseThrow(() -> new ResourceNotFoundException("Video not found"));
    }

    private Upload ownedUpload(String id, long user) {
        try { UUID.fromString(id); } catch (IllegalArgumentException e) {
            throw new ResourceNotFoundException("Upload not found");
        }
        return jdbc.query("SELECT folder_id,title,size_bytes,part_count,state,asset_id,expires_at " +
                "FROM prp_video_uploads WHERE id=? AND user_id=?",
                (rs, i) -> new Upload(rs.getObject(1, Long.class), rs.getString(2), rs.getLong(3),
                        rs.getInt(4), rs.getString(5), rs.getObject(6, Long.class),
                        rs.getTimestamp(7).toLocalDateTime()), id, user)
                .stream().findFirst().orElseThrow(() -> new ResourceNotFoundException("Upload not found"));
    }

    private void requireActive(Upload upload) {
        if (!"UPLOADING".equals(upload.state) || !upload.expiresAt.isAfter(LocalDateTime.now())) {
            throw new IllegalArgumentException("Upload expired or already completed");
        }
    }

    private void afterCommit(IoWork work) {
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                try {
                    work.perform();
                } catch (IOException e) {
                    log.warn("Video storage post-commit cleanup failed; will require retry", e);
                }
            }
        });
    }

    @FunctionalInterface
    private interface IoWork { void perform() throws IOException; }

    private record Asset(String storageKey, long sizeBytes) { }
    private record Upload(Long folderId, String title, long sizeBytes, int partCount,
                          String state, Long assetId, LocalDateTime expiresAt) { }
}
