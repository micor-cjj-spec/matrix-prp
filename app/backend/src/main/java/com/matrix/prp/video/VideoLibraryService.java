package com.matrix.prp.video;

import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.common.api.ResourceNotFoundException;
import com.matrix.prp.video.VideoDtos.*;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.sql.PreparedStatement;
import java.sql.Statement;
import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
@Profile("!test")
public class VideoLibraryService {
    public static final int CHUNK_SIZE = 8 * 1024 * 1024;
    private static final long MAX_FILE_SIZE = 2L * 1024 * 1024 * 1024;
    private static final long MAX_USER_STORAGE = 20L * 1024 * 1024 * 1024;

    private final JdbcTemplate jdbc;
    private final MediaTicketService tickets;
    private final Path root;
    private final RowMapper<Folder> folderRow = (rs, i) -> new Folder(rs.getLong("id"),
            rs.getObject("parent_id", Long.class), rs.getString("name"), rs.getInt("sort_order"));
    private final RowMapper<Video> videoRow = (rs, i) -> new Video(rs.getLong("id"),
            rs.getObject("folder_id", Long.class), rs.getString("title"), rs.getLong("size_bytes"),
            rs.getTimestamp("created_at").toLocalDateTime(), rs.getDouble("position_seconds"));

    public VideoLibraryService(JdbcTemplate jdbc, MediaTicketService tickets,
            @Value("${matrix-prp.video.storage-root:./data/videos}") String storageRoot) throws IOException {
        this.jdbc = jdbc;
        this.tickets = tickets;
        this.root = Path.of(storageRoot).toAbsolutePath().normalize();
        Files.createDirectories(root.resolve("media"));
        Files.createDirectories(root.resolve("temp"));
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
                "COALESCE(p.position_seconds,0) AS position_seconds FROM prp_video_assets a " +
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
        // A failed file deletion leaves an inaccessible orphan; routine storage GC will clean it up.
        Files.deleteIfExists(mediaPath(user, asset.storageKey));
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

    public Path authorizedMedia(long id, String token) {
        long user = tickets.verify(token, id);
        Asset asset = requireVideo(user, id);
        Path path = mediaPath(user, asset.storageKey);
        if (!Files.isRegularFile(path)) throw new ResourceNotFoundException("Video file is missing");
        return path;
    }

    public UploadSession beginUpload(UploadRequest request) {
        long user = CurrentUser.id();
        requireFolder(user, request.folderId());
        long size = request.sizeBytes();
        if (size > MAX_FILE_SIZE) throw new ResponseStatusException(HttpStatus.valueOf(413), "Video exceeds 2 GiB");
        Long used = jdbc.queryForObject("SELECT COALESCE(SUM(size_bytes),0) FROM prp_video_assets WHERE user_id=?",
                Long.class, user);
        if (used + size > MAX_USER_STORAGE) throw new ResponseStatusException(HttpStatus.valueOf(413), "Storage quota exceeded");
        int parts = (int) ((size + CHUNK_SIZE - 1) / CHUNK_SIZE);
        String id = UUID.randomUUID().toString();
        jdbc.update("INSERT INTO prp_video_uploads (id,user_id,folder_id,title,size_bytes,part_count,state,expires_at) " +
                        "VALUES (?,?,?,?,?,?,'UPLOADING',?)",
                id, user, request.folderId(), request.title().trim(), size, parts, LocalDateTime.now().plusHours(24));
        return new UploadSession(id, CHUNK_SIZE, parts);
    }

    public void writeChunk(String id, int number, byte[] contents) throws IOException {
        long user = CurrentUser.id();
        Upload upload = ownedUpload(id, user);
        requireActive(upload);
        if (number < 0 || number >= upload.partCount) throw new IllegalArgumentException("Invalid part number");
        long expected = number == upload.partCount - 1
                ? upload.sizeBytes - (long) number * CHUNK_SIZE : CHUNK_SIZE;
        if (contents.length != expected) throw new IllegalArgumentException("Incorrect chunk length");
        Path dir = uploadDir(user, id);
        Files.createDirectories(dir);
        Path tmp = Files.createTempFile(dir, "chunk-", ".writing");
        try {
            Files.write(tmp, contents);
            Files.move(tmp, dir.resolve(number + ".part"), StandardCopyOption.REPLACE_EXISTING);
        } finally {
            Files.deleteIfExists(tmp);
        }
    }

    @Transactional
    public synchronized Video completeUpload(String id) throws IOException {
        long user = CurrentUser.id();
        Upload upload = ownedUpload(id, user);
        if ("COMPLETE".equals(upload.state) && upload.assetId != null) {
            return findVideo(user, upload.assetId);
        }
        requireActive(upload);
        Path dir = uploadDir(user, id);
        for (int i = 0; i < upload.partCount; i++) {
            Path part = dir.resolve(i + ".part");
            long expected = i == upload.partCount - 1
                    ? upload.sizeBytes - (long) i * CHUNK_SIZE : CHUNK_SIZE;
            if (!Files.isRegularFile(part) || Files.size(part) != expected) {
                throw new IllegalArgumentException("Missing or invalid upload part: " + i);
            }
        }
        // The ISO BMFF ftyp signature is required for an MP4 container.
        try (var input = Files.newInputStream(dir.resolve("0.part"))) {
            byte[] header = input.readNBytes(8);
            if (header.length != 8 || header[4] != 'f' || header[5] != 't'
                    || header[6] != 'y' || header[7] != 'p') {
                throw new IllegalArgumentException("Only MP4 video is supported");
            }
        }
        String storageKey = UUID.randomUUID().toString();
        Path finalPath = mediaPath(user, storageKey);
        Files.createDirectories(finalPath.getParent());
        Path assembling = Files.createTempFile(finalPath.getParent(), "assembly-", ".tmp");
        try {
            try (OutputStream out = Files.newOutputStream(assembling)) {
                for (int i = 0; i < upload.partCount; i++) {
                    Files.copy(dir.resolve(i + ".part"), out);
                }
            }
            if (Files.size(assembling) != upload.sizeBytes) {
                throw new IllegalArgumentException("Total upload size mismatch");
            }
            Files.move(assembling, finalPath, StandardCopyOption.REPLACE_EXISTING);
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
            jdbc.update("UPDATE prp_video_uploads SET state='COMPLETE',asset_id=? " +
                    "WHERE id=? AND user_id=? AND state='UPLOADING'", assetId, id, user);
            // Temp cleanup is best effort; uploaded media is already readable.
            for (int i = 0; i < upload.partCount; i++) Files.deleteIfExists(dir.resolve(i + ".part"));
            Files.deleteIfExists(dir);
            return findVideo(user, assetId);
        } finally {
            Files.deleteIfExists(assembling);
        }
    }

    private Video findVideo(long user, long id) {
        return jdbc.query("SELECT a.id,a.folder_id,a.title,a.size_bytes,a.created_at, " +
                "COALESCE(p.position_seconds,0) AS position_seconds FROM prp_video_assets a " +
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

    private Path mediaPath(long user, String storageKey) {
        // storage keys are generated exclusively server-side UUIDs.
        return root.resolve("media").resolve(Long.toString(user)).resolve(storageKey + ".mp4");
    }

    private Path uploadDir(long user, String uploadId) {
        return root.resolve("temp").resolve(Long.toString(user)).resolve(uploadId);
    }

    private record Asset(String storageKey, long sizeBytes) { }
    private record Upload(Long folderId, String title, long sizeBytes, int partCount,
                          String state, Long assetId, LocalDateTime expiresAt) { }
}
