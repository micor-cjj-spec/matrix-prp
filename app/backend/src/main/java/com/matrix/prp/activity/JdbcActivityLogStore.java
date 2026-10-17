package com.matrix.prp.activity;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.List;
import org.springframework.context.annotation.Profile;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
@Component
@Profile("!test")
@EnableScheduling
public class JdbcActivityLogStore implements ActivityLogStore {
    private static final Logger LOG=LoggerFactory.getLogger(JdbcActivityLogStore.class);
    private static final int PURGE_BATCH=5000;
    private static final int MAX_PURGE_BATCHES=5;
    private final JdbcTemplate jdbc;
    public JdbcActivityLogStore(JdbcTemplate jdbc) { this.jdbc=jdbc; }
    @Override public void recordHttp(long userId,String method,String route,int status,long ms) {
        jdbc.update("INSERT INTO prp_api_request_log(user_id,http_method,route_pattern,status_code,elapsed_ms,created_at) VALUES(?,?,?,?,?,?)",
            userId,method,route,status,Math.max(0,ms),LocalDateTime.now(Clock.systemUTC()));
    }
    /** Retain 30 days of HTTP metadata; bounded batches avoid long-running transactions. */
    @Scheduled(initialDelayString="${matrix-prp.activity.cleanup-ms:3600000}",
               fixedDelayString="${matrix-prp.activity.cleanup-ms:3600000}")
    public void purgeExpired() {
        LocalDateTime cutoff=LocalDateTime.now(Clock.systemUTC()).minusDays(30);
        try {
            for(int batch=0;batch<MAX_PURGE_BATCHES;batch++) {
                int deleted=jdbc.update(
                    "DELETE FROM prp_api_request_log WHERE created_at < ? ORDER BY created_at,id LIMIT 5000",
                    cutoff);
                if(deleted<PURGE_BATCH) break;
            }
        } catch(RuntimeException ex) {
            LOG.warn("Could not purge expired HTTP request metadata; will retry on next maintenance tick");
        }
    }
    @Override public List<Entry> recent(long userId,int days,int limit) {
        LocalDateTime since=LocalDateTime.now(Clock.systemUTC()).minusDays(days);
        return jdbc.query("""
            SELECT kind,action,status,http_status,elapsed_ms,created_at FROM (
              SELECT 'HTTP' AS kind, CONCAT(http_method,' ',route_pattern) AS action,
                CAST(status_code AS CHAR) AS status,status_code AS http_status,elapsed_ms,created_at
              FROM prp_api_request_log WHERE user_id=? AND created_at>=?
              UNION ALL
              SELECT 'AI_TOOL' AS kind,tool_name AS action,status,NULL AS http_status,elapsed_ms,created_at
              FROM prp_ai_tool_audit WHERE user_id=? AND created_at>=?
            ) activity ORDER BY created_at DESC LIMIT ?
            """,(rs,i)->new Entry(rs.getString("kind"),rs.getString("action"),rs.getString("status"),
                rs.getObject("http_status",Integer.class),rs.getLong("elapsed_ms"),
                rs.getTimestamp("created_at").toLocalDateTime()),
            userId,since,userId,since,limit);
    }
}
