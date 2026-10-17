package com.matrix.prp.activity;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.List;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
@Component
@Profile("!test")
public class JdbcActivityLogStore implements ActivityLogStore {
    private final JdbcTemplate jdbc;
    public JdbcActivityLogStore(JdbcTemplate jdbc) { this.jdbc=jdbc; }
    @Override public void recordHttp(long userId,String method,String route,int status,long ms) {
        jdbc.update("INSERT INTO prp_api_request_log(user_id,http_method,route_pattern,status_code,elapsed_ms,created_at) VALUES(?,?,?,?,?,?)",
            userId,method,route,status,Math.max(0,ms),LocalDateTime.now(Clock.systemUTC()));
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
