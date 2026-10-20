package com.matrix.prp.ai;

import java.time.Clock;
import java.time.LocalDateTime;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/** Owner-scoped persisted request metrics, with a bounded 30-day retention policy. */
@Component
@Profile("!test")
public class JdbcAiInvocationAudit implements AiInvocationAudit {
    private static final Logger LOG = LoggerFactory.getLogger(JdbcAiInvocationAudit.class);
    private final JdbcTemplate db;

    public JdbcAiInvocationAudit(JdbcTemplate db) { this.db = db; }

    @Override public void record(Entry entry) {
        db.update("""
            INSERT INTO prp_ai_invocation_log
              (user_id,provider,model_id,credential_source,status,failure_category,
               elapsed_ms,first_token_ms,input_tokens,output_tokens,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, entry.userId(), entry.provider(), entry.model(), entry.credentialSource(),
            entry.status(), entry.failureCategory(), entry.elapsedMs(), entry.firstTokenMs(),
            entry.inputTokens(), entry.outputTokens(), entry.occurredAt());
    }

    @Override public List<Detail> recent(long userId, int days, int limit) {
        return db.query("""
            SELECT provider,model_id,credential_source,status,failure_category,
                   elapsed_ms,first_token_ms,input_tokens,output_tokens,created_at
              FROM prp_ai_invocation_log
             WHERE user_id=? AND created_at>=?
             ORDER BY created_at DESC,id DESC LIMIT ?
            """, (rs, i) -> new Detail(rs.getString("provider"), rs.getString("model_id"),
                rs.getString("credential_source"), rs.getString("status"),
                rs.getString("failure_category"), rs.getLong("elapsed_ms"),
                rs.getObject("first_token_ms", Long.class),
                rs.getObject("input_tokens", Long.class),
                rs.getObject("output_tokens", Long.class),
                rs.getTimestamp("created_at").toLocalDateTime()),
            userId, LocalDateTime.now(Clock.systemUTC()).minusDays(days), limit);
    }

    @Override public Summary summary(long userId, int days) {
        return db.queryForObject("""
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(status='SUCCESS'),0) AS succeeded,
                   COALESCE(SUM(status='FAILURE'),0) AS failed,
                   ROUND(AVG(elapsed_ms)) AS mean_elapsed,
                   ROUND(AVG(first_token_ms)) AS mean_first,
                   COALESCE(SUM(input_tokens),0) AS input_total,
                   COALESCE(SUM(output_tokens),0) AS output_total,
                   COALESCE(SUM(input_tokens IS NULL OR output_tokens IS NULL),0) AS missing_usage
              FROM prp_ai_invocation_log WHERE user_id=? AND created_at>=?
            """, (rs,i) -> new Summary(rs.getLong("total"), rs.getLong("succeeded"),
                rs.getLong("failed"), rs.getObject("mean_elapsed",Long.class),
                rs.getObject("mean_first",Long.class), rs.getLong("input_total"),
                rs.getLong("output_total"), rs.getLong("missing_usage")),
            userId, LocalDateTime.now(Clock.systemUTC()).minusDays(days));
    }

    @Scheduled(initialDelayString="${matrix-prp.ai.telemetry.cleanup-ms:3600000}",
               fixedDelayString="${matrix-prp.ai.telemetry.cleanup-ms:3600000}")
    public void purgeExpired() {
        var cutoff = LocalDateTime.now(Clock.systemUTC()).minusDays(30);
        try {
            for (int batch = 0; batch < 5; batch++) {
                int removed = db.update("""
                    DELETE FROM prp_ai_invocation_log WHERE created_at<?
                    ORDER BY created_at,id LIMIT 5000
                    """, cutoff);
                if (removed < 5000) break;
            }
        } catch (RuntimeException ex) {
            LOG.warn("AI telemetry cleanup unavailable; next maintenance run will retry");
        }
    }
}
