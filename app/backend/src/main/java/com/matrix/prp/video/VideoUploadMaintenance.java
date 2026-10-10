package com.matrix.prp.video;

import java.io.IOException;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * Safe to retry: mark expired rows first, delete the directory, then delete the row.
 * Failures keep the EXPIRED row so a subsequent run can retry.
 *
 * Designed for the current single-backend deployment. Multi-instance upload
 * concurrency requires a distributed lock before storage cleanup is enabled.
 */
@Component
@EnableScheduling
@Profile("!test")
public class VideoUploadMaintenance {
    private static final Logger log = LoggerFactory.getLogger(VideoUploadMaintenance.class);
    private final JdbcTemplate jdbc;
    private final VideoStorage storage;

    public VideoUploadMaintenance(JdbcTemplate jdbc, VideoStorage storage) {
        this.jdbc = jdbc;
        this.storage = storage;
    }

    @Scheduled(initialDelayString = "${matrix-prp.video.cleanup-delay-ms:3600000}",
               fixedDelayString = "${matrix-prp.video.cleanup-delay-ms:3600000}")
    public void scheduledCleanup() {
        cleanupExpiredUploads();
    }

    /** Processes at most 100 rows per run; returns the number of successful removals. */
    public int cleanupExpiredUploads() {
        List<Expired> expired = jdbc.query(
                "SELECT id,user_id FROM prp_video_uploads " +
                "WHERE state='EXPIRED' OR (state='UPLOADING' AND expires_at<CURRENT_TIMESTAMP(6)) " +
                "ORDER BY expires_at ASC LIMIT 100",
                (rs, row) -> new Expired(rs.getString("id"), rs.getLong("user_id")));
        int cleaned = 0;
        for (Expired row : expired) {
            try {
                jdbc.update("UPDATE prp_video_uploads SET state='EXPIRED' WHERE id=? AND user_id=? " +
                                "AND (state='EXPIRED' OR (state='UPLOADING' AND expires_at<CURRENT_TIMESTAMP(6)))",
                        row.id(), row.userId());
                Integer state = jdbc.queryForObject(
                        "SELECT COUNT(*) FROM prp_video_uploads WHERE id=? AND user_id=? AND state='EXPIRED'",
                        Integer.class, row.id(), row.userId());
                if (state == null || state != 1) continue;
                storage.removeUpload(row.userId(), row.id());
                cleaned += jdbc.update("DELETE FROM prp_video_uploads WHERE id=? AND user_id=? AND state='EXPIRED'",
                        row.id(), row.userId());
            } catch (IOException | RuntimeException exception) {
                log.warn("Could not clean expired video upload {}; will retry later", row.id(), exception);
            }
        }
        return cleaned;
    }

    private record Expired(String id, long userId) { }
}
