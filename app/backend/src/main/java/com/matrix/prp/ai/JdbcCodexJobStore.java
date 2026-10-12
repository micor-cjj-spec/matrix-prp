package com.matrix.prp.ai;

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
public class JdbcCodexJobStore implements CodexJobStore {
    private final JdbcTemplate db;
    public JdbcCodexJobStore(JdbcTemplate db) { this.db = db; }
    private static final RowMapper<Job> MAPPER = (rs, n) -> new Job(
        rs.getString("id"), rs.getLong("user_id"), rs.getString("repository"),
        rs.getString("task_type"), rs.getString("prompt"), rs.getString("status"),
        rs.getString("error_code"), rs.getObject("approved_by", Long.class),
        rs.getTimestamp("approved_at") == null ? null : rs.getTimestamp("approved_at").toLocalDateTime(),
        rs.getTimestamp("created_at").toLocalDateTime(),
        rs.getTimestamp("updated_at").toLocalDateTime());

    @Override public Job create(long user, String repository, String type, String prompt) {
        String id = UUID.randomUUID().toString();
        db.update("""
            INSERT INTO prp_ai_codex_jobs
            (id,user_id,repository,task_type,prompt,status,created_at,updated_at)
            VALUES (?,?,?,?,?,'PENDING_APPROVAL',UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))
            """, id,user,repository,type,prompt);
        return find(user,id).orElseThrow();
    }
    @Override public Optional<Job> find(long user, String id) {
        return db.query("SELECT * FROM prp_ai_codex_jobs WHERE id=? AND user_id=?",
            MAPPER,id,user).stream().findFirst();
    }
    @Override public List<Job> list(long user) {
        return db.query("SELECT * FROM prp_ai_codex_jobs WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
            MAPPER,user);
    }
    @Override public boolean claim(long user, String id, long approver) {
        return db.update("""
            UPDATE prp_ai_codex_jobs SET status='DISPATCHING',approved_by=?,
                approved_at=UTC_TIMESTAMP(6),updated_at=UTC_TIMESTAMP(6)
            WHERE id=? AND user_id=? AND status='PENDING_APPROVAL'
            """,approver,id,user)==1;
    }
    @Override public void dispatched(long user, String id) {
        db.update("""
            UPDATE prp_ai_codex_jobs SET status='DISPATCHED',error_code=NULL,updated_at=UTC_TIMESTAMP(6)
            WHERE id=? AND user_id=? AND status='DISPATCHING'
            """,id,user);
    }
    @Override public void fail(long user, String id, String code) {
        db.update("""
            UPDATE prp_ai_codex_jobs SET status='FAILED',error_code=?,updated_at=UTC_TIMESTAMP(6)
            WHERE id=? AND user_id=? AND status='DISPATCHING'
            """,code,id,user);
    }
    @Override public boolean cancel(long user, String id) {
        return db.update("""
            UPDATE prp_ai_codex_jobs SET status='CANCELLED',updated_at=UTC_TIMESTAMP(6)
            WHERE id=? AND user_id=? AND status='PENDING_APPROVAL'
            """,id,user)==1;
    }
}
