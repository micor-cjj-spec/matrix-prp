package com.matrix.prp.auth.repository;

import com.matrix.prp.auth.model.UserAccount;
import java.sql.PreparedStatement;
import java.sql.Statement;
import java.time.LocalDateTime;
import java.util.Optional;
import org.springframework.context.annotation.Profile;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
@Profile("!test")
public class JdbcUserStore implements UserStore {
    private static final RowMapper<UserAccount> USER_ROW = (rs, rowNum) ->
            new UserAccount(rs.getLong("id"), rs.getString("username"), rs.getString("display_name"),
                    rs.getString("password_hash"), rs.getBoolean("is_admin"), rs.getBoolean("enabled"));
    private final JdbcTemplate jdbc;

    public JdbcUserStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public Optional<UserAccount> findByUsername(String username) {
        return jdbc.query("SELECT * FROM prp_users WHERE username = ?", USER_ROW, username)
                .stream().findFirst();
    }

    @Override
    public Optional<UserAccount> findById(long id) {
        return jdbc.query("SELECT * FROM prp_users WHERE id = ?", USER_ROW, id)
                .stream().findFirst();
    }

    @Override
    public long countUsers() {
        return jdbc.queryForObject("SELECT COUNT(*) FROM prp_users", Long.class);
    }

    @Override
    public UserAccount create(String username, String displayName, String passwordHash, boolean administrator) {
        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            PreparedStatement statement = connection.prepareStatement(
                    "INSERT INTO prp_users (username, display_name, password_hash, is_admin, enabled) VALUES (?, ?, ?, ?, 1)",
                    Statement.RETURN_GENERATED_KEYS);
            statement.setString(1, username);
            statement.setString(2, displayName);
            statement.setString(3, passwordHash);
            statement.setBoolean(4, administrator);
            return statement;
        }, keyHolder);
        long id = keyHolder.getKey().longValue();
        return new UserAccount(id, username, displayName, passwordHash, administrator, true);
    }

    @Override
    public void addInvitation(String codeHash, long issuerUserId, LocalDateTime expiresAt) {
        jdbc.update("INSERT INTO prp_invitations (code_hash, issuer_user_id, expires_at) VALUES (?, ?, ?)",
                codeHash, issuerUserId, expiresAt);
    }

    @Override
    public boolean consumeInvitation(String codeHash, LocalDateTime now) {
        return jdbc.update("UPDATE prp_invitations SET used_at = ? WHERE code_hash = ? " +
                        "AND used_at IS NULL AND expires_at > ?", now, codeHash, now) == 1;
    }
    @Override
    @Transactional
    public UserAccount registerInvited(String username, String displayName, String passwordHash,
                                       String invitationHash, LocalDateTime now) {
        if (!consumeInvitation(invitationHash, now)) {
            throw new IllegalArgumentException("Invalid or expired invitation");
        }
        return create(username, displayName, passwordHash, false);
    }
}
