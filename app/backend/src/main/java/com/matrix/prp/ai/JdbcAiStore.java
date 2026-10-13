package com.matrix.prp.ai;

import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import java.sql.Statement;
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
    public long append(long userId, String conversationId, String role, String content) {
        GeneratedKeyHolder keys = new GeneratedKeyHolder();
        int affected = db.update(connection -> {
            var stmt=connection.prepareStatement("""
                INSERT INTO prp_ai_messages(conversation_id,role,content,created_at)
                SELECT id,?,?,? FROM prp_ai_conversations WHERE id=? AND user_id=?
                """, Statement.RETURN_GENERATED_KEYS);
            stmt.setString(1,role);
            stmt.setString(2,content);
            stmt.setObject(3,LocalDateTime.now(java.time.Clock.systemUTC()));
            stmt.setString(4,conversationId);
            stmt.setLong(5,userId);
            return stmt;
        },keys);
        if (affected!=1 || keys.getKey()==null)
            throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Conversation not found");
        db.update("UPDATE prp_ai_conversations SET updated_at=? WHERE id=? AND user_id=?",
            LocalDateTime.now(java.time.Clock.systemUTC()),conversationId,userId);
        return keys.getKey().longValue();
    }

    @Override
    @Transactional
    public void saveBlocks(long userId,String conversationId,long messageId,List<MessageBlock> blocks) {
        if (!owns(userId,conversationId))
            throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Conversation not found");
        Integer valid=db.queryForObject("""
            SELECT COUNT(*) FROM prp_ai_messages m
            JOIN prp_ai_conversations c ON m.conversation_id=c.id
            WHERE m.id=? AND m.role='assistant' AND c.id=? AND c.user_id=?
            """,Integer.class,messageId,conversationId,userId);
        if (valid==null || valid!=1)
            throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Assistant message not found");
        for (MessageBlock block:blocks) {
            if (!"navigation".equals(block.type()) || block.route().length()>300)
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Unsupported message block");
            db.update("""
                INSERT INTO prp_ai_message_blocks(message_id,user_id,block_type,module,label,route,created_at)
                VALUES (?,?,?,?,?,?,?)
                """,messageId,userId,block.type(),block.module(),block.label(),block.route(),
                LocalDateTime.now(java.time.Clock.systemUTC()));
        }
    }
    @Override
    public List<MessageBlock> blocks(long userId,String conversationId) {
        return db.query("""
            SELECT b.message_id,b.block_type,b.module,b.label,b.route
            FROM prp_ai_message_blocks b
            JOIN prp_ai_messages m ON m.id=b.message_id
            JOIN prp_ai_conversations c ON c.id=m.conversation_id
            WHERE c.id=? AND c.user_id=? AND b.user_id=?
            ORDER BY b.id DESC LIMIT 500
            """,(rs,n)->new MessageBlock(rs.getLong(1),rs.getString(2),rs.getString(3),
                rs.getString(4),rs.getString(5)),conversationId,userId,userId);
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
