package com.matrix.prp.ai;

import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Repository
@Profile("!test")
public class JdbcAiStore implements AiStore {
    private final JdbcTemplate db;
    public JdbcAiStore(JdbcTemplate db) { this.db = db; }

    @Override
    public Conversation create(long userId, String title) {
        String id = UUID.randomUUID().toString();
        LocalDateTime now = LocalDateTime.now(java.time.Clock.systemUTC());
        db.update("INSERT INTO prp_ai_conversations(id,user_id,title,created_at,updated_at) VALUES (?,?,?,?,?)",
                id, userId, title, now, now);
        return new Conversation(id, title, now);
    }

    @Override
    public List<Conversation> list(long userId) {
        return db.query("SELECT id,title,updated_at FROM prp_ai_conversations WHERE user_id=? ORDER BY updated_at DESC LIMIT 50",
                (rs, n) -> new Conversation(rs.getString(1), rs.getString(2), rs.getTimestamp(3).toLocalDateTime()), userId);
    }

    @Override
    public boolean owns(long userId, String conversationId) {
        Integer count = db.queryForObject("SELECT count(*) FROM prp_ai_conversations WHERE user_id=? AND id=?",
                Integer.class, userId, conversationId);
        return count != null && count > 0;
    }

    @Override
    public List<Message> messages(long userId, String conversationId, Long beforeId, int limit) {
        String cursorCondition = beforeId == null ? "" : " AND m.id<?";
        String sql = """
                SELECT m.id,m.role,m.content,m.created_at
                FROM prp_ai_messages m
                JOIN prp_ai_conversations c ON c.id=m.conversation_id
                WHERE c.user_id=? AND c.id=?
                """ + cursorCondition + " ORDER BY m.id DESC LIMIT ?";
        Object[] parameters = beforeId == null
                ? new Object[]{userId, conversationId, limit}
                : new Object[]{userId, conversationId, beforeId, limit};
        List<Message> recent = db.query(sql,
                (rs, n) -> new Message(rs.getLong(1), rs.getString(2), rs.getString(3),
                        rs.getTimestamp(4).toLocalDateTime()), parameters);
        java.util.Collections.reverse(recent);
        return recent;
    }

    @Override
    public void append(long userId, String conversationId, String role, String content) {
        int affected = db.update("""
                INSERT INTO prp_ai_messages(conversation_id,role,content,created_at)
                SELECT id,?,?,? FROM prp_ai_conversations WHERE id=? AND user_id=?
                """, role, content, LocalDateTime.now(java.time.Clock.systemUTC()), conversationId, userId);
        if (affected != 1) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Conversation not found");
        db.update("UPDATE prp_ai_conversations SET updated_at=? WHERE id=? AND user_id=?",
                LocalDateTime.now(java.time.Clock.systemUTC()), conversationId, userId);
    }

    @Override
    @Transactional
    public void reserve(long userId, String month, long tokens, int perUserRequests, long perUserTokens,
                        int globalRequests, long globalTokens) {
        reserveOne(0L, month, tokens, globalRequests, globalTokens);
        reserveOne(userId, month, tokens, perUserRequests, perUserTokens);
    }

    private void reserveOne(long subject, String month, long tokens, int maxRequests, long maxTokens) {
        db.update("INSERT IGNORE INTO prp_ai_usage(user_id,usage_month,requests,reserved_tokens,input_tokens,output_tokens) VALUES (?,?,0,0,0,0)",
                subject, month);
        int changed = db.update("""
                UPDATE prp_ai_usage SET requests=requests+1,reserved_tokens=reserved_tokens+?
                WHERE user_id=? AND usage_month=? AND requests<? AND reserved_tokens+?<=?
                """, tokens, subject, month, maxRequests, tokens, maxTokens);
        if (changed != 1) throw new ResponseStatusException(HttpStatus.TOO_MANY_REQUESTS, "Monthly AI allowance reached");
    }

    @Override
    @Transactional
    public void completed(long userId, String month, long input, long output) {
        db.update("UPDATE prp_ai_usage SET input_tokens=input_tokens+?,output_tokens=output_tokens+? WHERE user_id=? AND usage_month=?",
                input, output, userId, month);
        db.update("UPDATE prp_ai_usage SET input_tokens=input_tokens+?,output_tokens=output_tokens+? WHERE user_id=0 AND usage_month=?",
                input, output, month);
    }

    @Override
    public Usage usage(long userId, String month) {
        List<Usage> rows = db.query("""
                SELECT usage_month,requests,reserved_tokens,input_tokens,output_tokens
                FROM prp_ai_usage WHERE user_id=? AND usage_month=?
                """, (rs, n) -> new Usage(rs.getString(1), rs.getInt(2), rs.getLong(3),
                rs.getLong(4), rs.getLong(5)), userId, month);
        return rows.isEmpty() ? new Usage(month, 0, 0, 0, 0) : rows.getFirst();
    }
}
