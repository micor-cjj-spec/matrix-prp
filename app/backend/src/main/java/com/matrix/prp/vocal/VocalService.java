package com.matrix.prp.vocal;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.security.CurrentUser;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
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
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@Service
@Profile("!test")
public class VocalService {
    private static final long MAX_BYTES = 12L * 1024 * 1024;
    private static final long QUOTA_BYTES = 256L * 1024 * 1024;
    public record Take(long id, String exerciseCode, String note, int durationSeconds,
                       long sizeBytes, VocalAnalysis.Summary analysis, String aiFeedback,
                       String aiStatus, LocalDateTime createdAt) {}
    public record Audio(Path file, String mimeType, long size) {}
    private record Stored(long id, String exercise, String note, int duration, long size,
                          String analysis, String feedback, String status, LocalDateTime created) {}
    private final JdbcTemplate jdbc;
    private final ObjectMapper json;
    private final Path root;
    private final RowMapper<Stored> row = (rs,i) -> new Stored(rs.getLong("id"),
        rs.getString("exercise_code"), rs.getString("note"), rs.getInt("duration_seconds"),
        rs.getLong("size_bytes"), rs.getString("analysis_json"), rs.getString("ai_feedback"),
        rs.getString("ai_status"), rs.getTimestamp("created_at").toLocalDateTime());

    public VocalService(JdbcTemplate jdbc, ObjectMapper json,
            @Value("${matrix-prp.vocal.storage-root:./data/vocal}") String root) {
        this.jdbc = jdbc; this.json = json; this.root = Path.of(root).toAbsolutePath().normalize();
    }
    public List<java.util.Map<String,Object>> exercises() { return VocalAnalysis.exercises(); }
    public List<Take> list() {
        return jdbc.query("SELECT id,exercise_code,note,duration_seconds,size_bytes,analysis_json,ai_feedback,ai_status,created_at "
            + "FROM prp_vocal_takes WHERE user_id=? ORDER BY created_at DESC,id DESC LIMIT 100",
            row, CurrentUser.id()).stream().map(this::present).toList();
    }
    private Take present(Stored s) {
        try {
            return new Take(s.id(),s.exercise(),s.note(),s.duration(),s.size(),
                json.readValue(s.analysis(), VocalAnalysis.Summary.class),s.feedback(),s.status(),s.created());
        } catch (IOException ex) { throw new IllegalStateException("Invalid stored vocal analysis",ex); }
    }
    private Path path(long user, String key) {
        if (!key.matches("[0-9a-f-]{36}\\.(webm|m4a|ogg|wav)"))
            throw new IllegalStateException("Invalid media identifier");
        return root.resolve(Long.toString(user)).resolve(key).normalize();
    }
    private String extension(byte[] head) {
        if (head.length >= 4 && (head[0]&255)==0x1a && (head[1]&255)==0x45
                && (head[2]&255)==0xdf && (head[3]&255)==0xa3) return "webm";
        if (head.length >= 8 && head[4]=='f' && head[5]=='t' && head[6]=='y' && head[7]=='p') return "m4a";
        if (head.length >= 4 && head[0]=='O' && head[1]=='g' && head[2]=='g' && head[3]=='S') return "ogg";
        if (head.length >= 12 && head[0]=='R' && head[1]=='I' && head[2]=='F' && head[3]=='F'
                && head[8]=='W' && head[9]=='A' && head[10]=='V' && head[11]=='E') return "wav";
        throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Unsupported audio file");
    }
    @Transactional
    public Take upload(String code, String note, int seconds, String observations,
                       MultipartFile file) throws IOException {
        long user = CurrentUser.id();
        Double target = VocalAnalysis.targetFor(code);
        if (seconds < 1 || seconds > 600 || note != null && note.length() > 500)
            throw new IllegalArgumentException("Invalid recording metadata");
        if (file == null || file.isEmpty() || file.getSize() > MAX_BYTES)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Recording must be 1–12 MiB");
        if (observations == null || observations.length() > 90000)
            throw new IllegalArgumentException("Invalid pitch data");
        List<VocalAnalysis.Point> points = json.readValue(observations,
            new TypeReference<List<VocalAnalysis.Point>>() {});
        VocalAnalysis.Summary summary = VocalAnalysis.summarize(points,target);
        // Serialize before writing media, so bad inputs cannot leave a file behind.
        String metrics = json.writeValueAsString(summary);
        String mime = file.getContentType();
        if (mime == null || !List.of("audio/webm","audio/mp4","audio/ogg","audio/wav",
            "audio/x-wav","video/mp4").contains(mime.split(";")[0].toLowerCase()))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Invalid audio content type");
        byte[] header;
        try (var input = file.getInputStream()) { header = input.readNBytes(16); }
        String ext = extension(header);
        if (!((ext.equals("webm") && mime.startsWith("audio/webm")) ||
            (ext.equals("m4a") && (mime.startsWith("audio/mp4") || mime.startsWith("video/mp4"))) ||
            (ext.equals("ogg") && mime.startsWith("audio/ogg")) ||
            (ext.equals("wav") && mime.contains("wav"))))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Audio type/header mismatch");
        // Lock user row to serialize quota checks and prevent concurrent overage.
        var owners = jdbc.queryForList("SELECT id FROM prp_users WHERE id=? FOR UPDATE",Long.class,user);
        if (owners.isEmpty()) throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        long used = jdbc.queryForObject("SELECT COALESCE(SUM(size_bytes),0) FROM prp_vocal_takes WHERE user_id=?",
            Long.class,user);
        if (used + file.getSize() > QUOTA_BYTES)
            throw new ResponseStatusException(HttpStatus.PAYLOAD_TOO_LARGE,"Voice storage quota exceeded");
        String key = UUID.randomUUID() + "." + ext;
        Path output = path(user,key);
        Files.createDirectories(output.getParent());
        Path temp = Files.createTempFile(output.getParent(),"upload-",".part");
        try {
            try (var in=file.getInputStream()) { Files.copy(in,temp,StandardCopyOption.REPLACE_EXISTING); }
            if (Files.size(temp)!=file.getSize()) throw new IOException("Incomplete upload");
            Files.move(temp,output,StandardCopyOption.ATOMIC_MOVE);
            if (TransactionSynchronizationManager.isSynchronizationActive()) {
                TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                    @Override public void afterCompletion(int status) {
                        if (status!=STATUS_COMMITTED) {
                            try { Files.deleteIfExists(output); } catch (IOException ignored) {}
                        }
                    }
                });
            }
            GeneratedKeyHolder holder = new GeneratedKeyHolder();
            String clean = note == null ? "" : note.trim();
            jdbc.update(c -> {
                PreparedStatement ps=c.prepareStatement("INSERT INTO prp_vocal_takes "
                    +"(user_id,exercise_code,note,duration_seconds,mime_type,storage_key,size_bytes,analysis_json) "
                    +"VALUES (?,?,?,?,?,?,?,?)",Statement.RETURN_GENERATED_KEYS);
                ps.setLong(1,user);ps.setString(2,code);ps.setString(3,clean);ps.setInt(4,seconds);
                ps.setString(5,"audio/"+ext);ps.setString(6,key);ps.setLong(7,file.getSize());
                ps.setString(8,metrics);return ps;
            },holder);
            long id=holder.getKey().longValue();
            return present(jdbc.query("SELECT id,exercise_code,note,duration_seconds,size_bytes,analysis_json,ai_feedback,ai_status,created_at "
                    +"FROM prp_vocal_takes WHERE id=? AND user_id=?",row,id,user).getFirst());
        } catch (Exception ex) {
            Files.deleteIfExists(output);
            if (ex instanceof IOException io) throw io;
            if (ex instanceof RuntimeException rt) throw rt;
            throw new IOException(ex);
        } finally { Files.deleteIfExists(temp); }
    }
    public Audio audio(long id) {
        long user=CurrentUser.id();
        List<java.util.Map<String,Object>> rows=jdbc.queryForList(
            "SELECT storage_key,mime_type,size_bytes FROM prp_vocal_takes WHERE id=? AND user_id=?",id,user);
        if(rows.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Recording not found");
        var r=rows.getFirst();
        String ext=((String)r.get("storage_key")).substring(((String)r.get("storage_key")).lastIndexOf('.')+1);
        String type=ext.equals("m4a") ? "audio/mp4" : "audio/"+ext;
        Path file=path(user,(String)r.get("storage_key"));
        if(!Files.isRegularFile(file)) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Audio missing");
        return new Audio(file,type,((Number)r.get("size_bytes")).longValue());
    }
    @Transactional
    public void delete(long id) {
        long user=CurrentUser.id();
        var rows=jdbc.queryForList("SELECT storage_key FROM prp_vocal_takes WHERE id=? AND user_id=? FOR UPDATE",id,user);
        if(rows.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Recording not found");
        Path file=path(user,(String)rows.getFirst().get("storage_key"));
        jdbc.update("DELETE FROM prp_vocal_takes WHERE id=? AND user_id=?",id,user);
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override public void afterCommit() {
                try { Files.deleteIfExists(file); } catch (IOException ignored) { /* retain orphan for reconciliation */ }
            }
        });
    }
    public Take get(long id) {
        var rows=jdbc.query("SELECT id,exercise_code,note,duration_seconds,size_bytes,analysis_json,ai_feedback,ai_status,created_at "
             +"FROM prp_vocal_takes WHERE id=? AND user_id=?",row,id,CurrentUser.id());
        if(rows.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Recording not found");
        return present(rows.getFirst());
    }
    public boolean claimAnalysis(long id) {
        return jdbc.update("UPDATE prp_vocal_takes SET ai_status='PROCESSING',ai_started_at=CURRENT_TIMESTAMP "
          +"WHERE id=? AND user_id=? AND (ai_status IN ('NEW','FAILED') "
          +"OR (ai_status='PROCESSING' AND ai_started_at < DATE_SUB(NOW(),INTERVAL 5 MINUTE)))",
          id,CurrentUser.id())==1;
    }
    public void finishAnalysis(long id,String feedback,boolean ok) {
        jdbc.update("UPDATE prp_vocal_takes SET ai_status=?,ai_feedback=? WHERE id=? AND user_id=?",
            ok?"DONE":"FAILED",feedback,id,CurrentUser.id());
    }
}
