package com.matrix.prp.ai;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
@Profile("!test")
public class JdbcAgentTaskStore implements AgentTaskStore {
    private final JdbcTemplate db;
    public JdbcAgentTaskStore(JdbcTemplate db) { this.db = db; }
    private static final RowMapper<AgentTask> MAPPER = (rs, n) -> new AgentTask(
        rs.getString("id"), rs.getLong("user_id"), rs.getString("task_type"),
        rs.getString("prompt"), rs.getString("status"), rs.getString("result"),
        rs.getString("error_code"), rs.getTimestamp("created_at").toLocalDateTime(),
        rs.getTimestamp("updated_at").toLocalDateTime(),
        rs.getObject("approved_by") == null ? null : rs.getLong("approved_by"),
        timestamp(rs, "approved_at"), rs.getString("session_ref"));
    private static LocalDateTime timestamp(ResultSet rs, String col) throws SQLException {
        var value = rs.getTimestamp(col);
        return value == null ? null : value.toLocalDateTime();
    }
    @Override public AgentTask create(long user, String type, String prompt) {
        String id = UUID.randomUUID().toString();
        String session = "prp:" + user + ":" + id;
        db.update("""
            INSERT INTO prp_ai_agent_tasks
            (id,user_id,task_type,prompt,status,session_ref,created_at,updated_at)
            VALUES (?,?,?,?,'PENDING_APPROVAL',?,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))
            """, id, user, type, prompt, session);
        return find(user, id).orElseThrow();
    }
    @Override public Optional<AgentTask> find(long user, String id) {
        return db.query("SELECT * FROM prp_ai_agent_tasks WHERE id=? AND user_id=?",
            MAPPER, id, user).stream().findFirst();
    }
    @Override public List<AgentTask> list(long user) {
        return db.query("SELECT * FROM prp_ai_agent_tasks WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
            MAPPER, user);
    }
    @Override public boolean claim(long user, String id, long approver) {
        return db.update("""
            UPDATE prp_ai_agent_tasks SET status='RUNNING', approved_by=?,
                approved_at=UTC_TIMESTAMP(6),updated_at=UTC_TIMESTAMP(6)
            WHERE id=? AND user_id=? AND status='PENDING_APPROVAL'
            """, approver, id, user) == 1;
    }
    @Override public void complete(long user, String id, String result) {
        db.update("""
            UPDATE prp_ai_agent_tasks SET status='COMPLETED', result=?,error_code=NULL,updated_at=UTC_TIMESTAMP(6)
            WHERE id=? AND user_id=? AND status='RUNNING'
            """, result, id, user);
    }
    @Override public void fail(long user, String id, String code) {
        db.update("""
            UPDATE prp_ai_agent_tasks SET status='FAILED',error_code=?,updated_at=UTC_TIMESTAMP(6)
            WHERE id=? AND user_id=? AND status='RUNNING'
            """, code, id, user);
    }
    @Override public boolean cancel(long user, String id) {
        return db.update("""
            UPDATE prp_ai_agent_tasks SET status='CANCELLED',updated_at=UTC_TIMESTAMP(6)
            WHERE id=? AND user_id=? AND status='PENDING_APPROVAL'
            """, id, user) == 1;
    }
}
