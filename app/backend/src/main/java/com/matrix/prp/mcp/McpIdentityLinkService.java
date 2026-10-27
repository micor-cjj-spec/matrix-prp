package com.matrix.prp.mcp;

import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.auth.security.LoginAttemptLimiter;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.LocalDateTime;
import java.util.Base64;
import java.util.HexFormat;
import java.util.List;
import java.util.OptionalLong;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/**
 * Two independent proofs before associating PRP and OAuth identity:
 * (1) PRP owner + password creates a high-entropy, client-bound ticket.
 * (2) a bearer validated by OAuth JWT verifier supplies (issuer, sub, client_id).
 * No caller may supply a PRP user ID or an unverified OAuth subject.
 */
@Service
@ConditionalOnProperty(prefix = "matrix-prp.mcp.oauth", name = "enabled", havingValue = "true")
public class McpIdentityLinkService {
    public record Ticket(String code, String clientId, String expiresAt) {}
    public record Link(String issuer, String subject, boolean newlyLinked) {}
    private record Pending(long userId, String clientId, LocalDateTime expiresAt, boolean consumed) {}

    private final JdbcTemplate db;
    private final UserStore users;
    private final PasswordEncoder passwords;
    private final LoginAttemptLimiter attempts;
    private final McpClientGrantService grants;
    private final String issuer;
    private final SecureRandom random = new SecureRandom();

    public McpIdentityLinkService(JdbcTemplate db, UserStore users,
                                  PasswordEncoder passwords, LoginAttemptLimiter attempts,
                                  McpClientGrantService grants,
                                  @Value("${matrix-prp.mcp.oauth.issuer:}") String issuer) {
        this.db = db;
        this.users = users;
        this.passwords = passwords;
        this.attempts = attempts;
        this.grants = grants;
        this.issuer = McpOAuthResourceServerConfig.strictHttps(issuer, "MCP OAuth issuer");
    }

    /** The PRP owner opens this only in PRP; codes are never logged or stored in plaintext. */
    @Transactional
    public Ticket issueTicket(String clientId, String password) {
        long owner = CurrentUser.id();
        if (grants.grantedScopes(owner, clientId).isEmpty())
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Authorize this OAuth client first");
        UserAccount account = users.findById(owner).orElse(null);
        if (account == null || !account.enabled())
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "PRP account unavailable");
        attempts.assertAllowed("mcp-identity-ticket", account.username());
        if (password == null || password.length() > 256
            || !passwords.matches(password, account.passwordHash())) {
            attempts.recordFailure("mcp-identity-ticket", account.username());
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "PRP reauthentication failed");
        }
        attempts.recordSuccess("mcp-identity-ticket", account.username());
        Integer count = db.queryForObject("SELECT COUNT(*) FROM prp_mcp_link_tickets " +
            "WHERE user_id=? AND consumed_at IS NULL AND expires_at > CURRENT_TIMESTAMP",
            Integer.class, owner);
        if (count != null && count >= 3)
            throw new ResponseStatusException(HttpStatus.TOO_MANY_REQUESTS, "Too many active identity tickets");

        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        String code = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        LocalDateTime expires = LocalDateTime.now().plusMinutes(10);
        db.update("INSERT INTO prp_mcp_link_tickets (ticket_hash,user_id,client_id,expires_at) VALUES (?,?,?,?)",
            hash(code), owner, clientId, java.sql.Timestamp.valueOf(expires));
        return new Ticket(code, clientId, expires.toString());
    }

    /** Called only after the dedicated OAuth security chain verified the bearer. */
    @Transactional
    public Link complete(String code, String verifiedIssuer, String verifiedSubject, String signedClientId) {
        if (code == null || !code.matches("[A-Za-z0-9_-]{43}"))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid linking code");
        if (!issuer.equals(verifiedIssuer) || verifiedSubject == null ||
            verifiedSubject.isBlank() || verifiedSubject.length() > 255 ||
            signedClientId == null || signedClientId.isBlank())
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Invalid verified OAuth identity");
        List<Pending> pending = db.query("SELECT user_id,client_id,expires_at,consumed_at " +
            "FROM prp_mcp_link_tickets WHERE ticket_hash=? FOR UPDATE",
            (rs, i) -> new Pending(rs.getLong("user_id"), rs.getString("client_id"),
                rs.getTimestamp("expires_at").toLocalDateTime(),
                rs.getTimestamp("consumed_at") != null), hash(code));
        if (pending.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Link ticket unavailable");
        Pending ticket = pending.getFirst();
        if (ticket.consumed() || !ticket.expiresAt().isAfter(LocalDateTime.now())
            || !ticket.clientId().equals(signedClientId))
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Ticket expired, consumed or client mismatched");
        if (grants.grantedScopes(ticket.userId(), signedClientId).isEmpty())
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "OAuth client grant was revoked");
        UserAccount account = users.findById(ticket.userId()).orElse(null);
        if (account == null || !account.enabled())
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Linked PRP account unavailable");

        List<Long> owners = db.query("SELECT user_id FROM prp_mcp_identity_links " +
            "WHERE issuer=? AND subject=? FOR UPDATE",
            (rs, i) -> rs.getLong(1), issuer, verifiedSubject);
        if (!owners.isEmpty() && owners.getFirst() != ticket.userId())
            throw new ResponseStatusException(HttpStatus.CONFLICT, "OAuth identity already linked");
        List<String> subjectForOwner = db.query("SELECT subject FROM prp_mcp_identity_links " +
            "WHERE user_id=? AND issuer=? FOR UPDATE",
            (rs, i) -> rs.getString(1), ticket.userId(), issuer);
        if (!subjectForOwner.isEmpty() && !subjectForOwner.getFirst().equals(verifiedSubject))
            throw new ResponseStatusException(HttpStatus.CONFLICT, "PRP account already linked to another OAuth identity");
        boolean inserted = owners.isEmpty();
        if (inserted) {
            db.update("INSERT INTO prp_mcp_identity_links (issuer,subject,user_id) VALUES (?,?,?)",
                issuer, verifiedSubject, ticket.userId());
        }
        if (db.update("UPDATE prp_mcp_link_tickets SET consumed_at=CURRENT_TIMESTAMP " +
            "WHERE ticket_hash=? AND consumed_at IS NULL", hash(code)) != 1)
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Link ticket already consumed");
        return new Link(issuer, verifiedSubject, inserted);
    }

    /**
     * Finish PRP-initiated PKCE linking ONLY after the separate first-party
     * flow verified the signed Keycloak ID token and consumed its one-time
     * state. The caller supplies the PRP owner from first-party JWT, never a
     * browser-provided user ID. Unique DB keys reject concurrent collisions.
     */
    @Transactional
    public boolean linkFirstPartyOwner(long owner, String verifiedIssuer,
                                       String subject, String intendedClientId) {
        if (owner <= 0 || !issuer.equals(verifiedIssuer)
                || subject == null || subject.isBlank() || subject.length() > 255
                || !McpFirstPartyOidcLinkService.CHATGPT_CLIENT_ID.equals(intendedClientId))
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED,
                "Invalid first-party OIDC linking identity");
        UserAccount account = users.findById(owner).orElse(null);
        if (account == null || !account.enabled())
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "PRP owner unavailable");
        if (!grants.grantedScopes(owner, intendedClientId).contains("prp.tasks.read"))
            throw new ResponseStatusException(HttpStatus.FORBIDDEN,
                "ChatGPT task permission not approved");
        List<Long> existingOwner = db.query(
            "SELECT user_id FROM prp_mcp_identity_links WHERE issuer=? AND subject=? FOR UPDATE",
            (rs, i) -> rs.getLong(1), issuer, subject);
        if (!existingOwner.isEmpty() && existingOwner.getFirst() != owner)
            throw new ResponseStatusException(HttpStatus.CONFLICT,
                "This OIDC identity is linked to another PRP account");
        List<String> existingSubject = db.query(
            "SELECT subject FROM prp_mcp_identity_links WHERE user_id=? AND issuer=? FOR UPDATE",
            (rs, i) -> rs.getString(1), owner, issuer);
        if (!existingSubject.isEmpty() && !existingSubject.getFirst().equals(subject))
            throw new ResponseStatusException(HttpStatus.CONFLICT,
                "PRP owner already linked to another OIDC identity");
        if (existingOwner.isEmpty() && existingSubject.isEmpty()) {
            try {
                db.update("INSERT INTO prp_mcp_identity_links (issuer,subject,user_id) VALUES (?,?,?)",
                    issuer, subject, owner);
            } catch (org.springframework.dao.DuplicateKeyException conflict) {
                throw new ResponseStatusException(HttpStatus.CONFLICT,
                    "Concurrent OIDC mapping already exists");
            }
            return true;
        }
        return false;
    }

    /** A verified OAuth issuer + subject, not a client-provided PRP ID, chooses owner. */
    public OptionalLong resolveUserId(String verifiedIssuer, String verifiedSubject) {
        if (!issuer.equals(verifiedIssuer) || verifiedSubject == null || verifiedSubject.isBlank())
            return OptionalLong.empty();
        List<Long> matches = db.query(
            "SELECT user_id FROM prp_mcp_identity_links WHERE issuer=? AND subject=?",
            (rs, i) -> rs.getLong(1), issuer, verifiedSubject);
        return matches.isEmpty() ? OptionalLong.empty() : OptionalLong.of(matches.getFirst());
    }

    public List<Link> myLinks() {
        long owner = CurrentUser.id();
        return db.query("SELECT issuer,subject FROM prp_mcp_identity_links WHERE user_id=? ORDER BY issuer",
            (rs, i) -> new Link(rs.getString(1), rs.getString(2), false), owner);
    }

    @Transactional
    public void unlink(String password) {
        long owner = CurrentUser.id();
        UserAccount account = users.findById(owner).orElse(null);
        if (account == null || !account.enabled())
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        attempts.assertAllowed("mcp-identity-unlink", account.username());
        if (password == null || !passwords.matches(password, account.passwordHash())) {
            attempts.recordFailure("mcp-identity-unlink", account.username());
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "PRP reauthentication failed");
        }
        attempts.recordSuccess("mcp-identity-unlink", account.username());
        db.update("DELETE FROM prp_mcp_identity_links WHERE user_id=? AND issuer=?", owner, issuer);
        db.update("DELETE FROM prp_mcp_link_tickets WHERE user_id=? AND consumed_at IS NULL", owner);
    }

    private static String hash(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(value.getBytes(StandardCharsets.US_ASCII));
            return HexFormat.of().formatHex(digest);
        } catch (java.security.NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("JVM SHA-256 unavailable", impossible);
        }
    }
}
