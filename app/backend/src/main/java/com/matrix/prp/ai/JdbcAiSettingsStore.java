package com.matrix.prp.ai;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
@Profile("!test")
public class JdbcAiSettingsStore implements AiSettingsStore {
    private final JdbcTemplate db;
    public JdbcAiSettingsStore(JdbcTemplate db) { this.db = db; }
    @Override public Optional<Selection> selection(long user) {
        List<Selection> rows = db.query(
            "SELECT provider_id, model_id FROM prp_ai_preferences WHERE user_id=?",
            (rs, n) -> new Selection(rs.getString(1), rs.getString(2)), user);
        return rows.stream().findFirst();
    }
    @Override public Map<String, String> encryptedKeys(long user) {
        Map<String, String> keys = new HashMap<>();
        db.query("SELECT provider_id, encrypted_api_key FROM prp_ai_provider_credentials WHERE user_id=?",
            rs -> { keys.put(rs.getString(1), rs.getString(2)); }, user);
        return keys;
    }
    @Override public void putKey(long user, String provider, String ciphertext) {
        db.update("""
          INSERT INTO prp_ai_provider_credentials(user_id,provider_id,encrypted_api_key,updated_at)
          VALUES (?,?,?,UTC_TIMESTAMP(6))
          ON DUPLICATE KEY UPDATE encrypted_api_key=VALUES(encrypted_api_key),updated_at=UTC_TIMESTAMP(6)
          """, user, provider, ciphertext);
    }
    @Override public void deleteKey(long user, String provider) {
        db.update("DELETE FROM prp_ai_provider_credentials WHERE user_id=? AND provider_id=?", user, provider);
    }
    @Override public void select(long user, String provider, String model) {
        db.update("""
          INSERT INTO prp_ai_preferences(user_id,provider_id,model_id,updated_at)
          VALUES (?,?,?,UTC_TIMESTAMP(6))
          ON DUPLICATE KEY UPDATE provider_id=VALUES(provider_id),model_id=VALUES(model_id),updated_at=UTC_TIMESTAMP(6)
          """, user, provider, model);
    }
}
