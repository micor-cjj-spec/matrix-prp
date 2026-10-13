package com.matrix.prp.ai;

import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import java.time.LocalDateTime;
import java.time.Clock;

@Component
@Profile("!test")
public class JdbcAiToolAudit implements AiToolAudit {
    private final JdbcTemplate db;
    public JdbcAiToolAudit(JdbcTemplate db) { this.db=db; }
    @Override public void record(long userId,String conversationId,String tool,String scope,String status,long elapsedMs) {
        db.update("INSERT INTO prp_ai_tool_audit(user_id,conversation_id,tool_name,scope,status,elapsed_ms,created_at) VALUES (?,?,?,?,?,?,?)",
            userId,conversationId,tool,scope,status,elapsedMs,LocalDateTime.now(Clock.systemUTC()));
    }
}
