package com.matrix.prp.mcp;

import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.auth.security.LoginAttemptLimiter;
import java.util.Arrays;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Collectors;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

/**
 * Server-side user consent allowlist for the issuer-signed OAuth client_id.
 * An issuer JWT alone never authorizes MCP access: the owner can revoke a
 * client or reduce its scopes and the very next tool request observes it.
 */
@Service
@ConditionalOnProperty(prefix = "matrix-prp.mcp.oauth", name = "enabled", havingValue = "true")
public class McpClientGrantService {
    public record Grant(String clientId, List<String> scopes, String status) {}
    private final JdbcTemplate db;
    private final UserStore users;
    private final PasswordEncoder encoder;
    private final LoginAttemptLimiter limiter;

    public McpClientGrantService(JdbcTemplate db, UserStore users,
                                 PasswordEncoder encoder, LoginAttemptLimiter limiter) {
        this.db = db; this.users = users; this.encoder = encoder; this.limiter = limiter;
    }

    private static String client(String clientId) {
        if (clientId == null || !clientId.matches("[A-Za-z0-9][A-Za-z0-9._~:/-]{1,127}"))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid OAuth client ID");
        return clientId;
    }

    private static Set<String> scopes(List<String> selected) {
        if (selected == null || selected.isEmpty() || selected.size() > McpOAuthMetadataController.SCOPES.size())
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid MCP scope selection");
        var result = new TreeSet<String>();
        for (String scope : selected) {
            if (!McpOAuthMetadataController.SCOPES.contains(scope) || !result.add(scope))
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Unsupported or duplicate MCP scope");
        }
        return result;
    }

    public List<Grant> mine() {
        long owner = CurrentUser.id();
        return db.query("SELECT client_id,scopes,status FROM prp_mcp_client_grants WHERE user_id=? ORDER BY client_id",
            (rs, row) -> new Grant(rs.getString("client_id"),
                Arrays.asList(rs.getString("scopes").split(",")), rs.getString("status")), owner);
    }

    public Grant authorize(String clientId, List<String> requested, String password) {
        long owner = CurrentUser.id();
        String id = client(clientId);
        Set<String> approved = scopes(requested);
        UserAccount account = users.findById(owner).orElse(null);
        if (account == null || !account.enabled()) throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        limiter.assertAllowed("mcp-client-grant", account.username());
        if (password == null || password.length() > 256 || !encoder.matches(password, account.passwordHash())) {
            limiter.recordFailure("mcp-client-grant", account.username());
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Account reauthentication failed");
        }
        limiter.recordSuccess("mcp-client-grant", account.username());
        String csv = String.join(",", approved);
        Integer count = db.queryForObject(
            "SELECT COUNT(*) FROM prp_mcp_client_grants WHERE user_id=? AND status='ACTIVE'",
            Integer.class, owner);
        Integer exists = db.queryForObject(
            "SELECT COUNT(*) FROM prp_mcp_client_grants WHERE user_id=? AND client_id=? AND status='ACTIVE'",
            Integer.class, owner, id);
        if (count != null && count >= 12 && (exists == null || exists == 0))
            throw new ResponseStatusException(HttpStatus.TOO_MANY_REQUESTS, "Too many connected MCP clients");
        db.update("INSERT INTO prp_mcp_client_grants (user_id,client_id,scopes,status) VALUES (?,?,?,'ACTIVE') " +
            "ON DUPLICATE KEY UPDATE scopes=VALUES(scopes),status='ACTIVE',updated_at=CURRENT_TIMESTAMP",
            owner, id, csv);
        return new Grant(id, List.copyOf(approved), "ACTIVE");
    }

    public void revoke(String clientId) {
        long owner = CurrentUser.id();
        db.update("UPDATE prp_mcp_client_grants SET status='REVOKED',updated_at=CURRENT_TIMESTAMP " +
            "WHERE user_id=? AND client_id=? AND status='ACTIVE'", owner, client(clientId));
    }

    /** Called on every bearer authentication, never cached across requests. */
    public Set<String> grantedScopes(long userId, String clientId) {
        if (userId <= 0 || clientId == null || !clientId.matches("[A-Za-z0-9][A-Za-z0-9._~:/-]{1,127}"))
            return Set.of();
        List<String> raw = db.query(
            "SELECT scopes FROM prp_mcp_client_grants WHERE user_id=? AND client_id=? AND status='ACTIVE'",
            (rs, i) -> rs.getString(1), userId, clientId);
        if (raw.isEmpty()) return Set.of();
        return Arrays.stream(raw.getFirst().split(","))
            .filter(McpOAuthMetadataController.SCOPES::contains)
            .collect(Collectors.toUnmodifiableSet());
    }
}
