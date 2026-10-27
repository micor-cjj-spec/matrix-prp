package com.matrix.prp.mcp;

import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.auth.security.LoginAttemptLimiter;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Base64;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.util.UriComponentsBuilder;

/**
 * Opt-in PRP first-party account-link bootstrap, independent of ChatGPT's OAuth
 * client. Only PRP's authenticated owner/password can initiate and finish it.
 * The ID token is validated SERVER SIDE; never returned to the browser.
 *
 * Keycloak MUST have a separately reviewed public, authorization-code-only
 * client with exact redirect and S256, and consistent (issuer, sub) with the
 * confidential ChatGPT client. The feature defaults OFF.
 */
@Service
@ConditionalOnProperty(prefix = "matrix-prp.mcp.oauth.first-party-link",
                       name = "enabled", havingValue = "true")
public class McpFirstPartyOidcLinkService {
    public record Begin(String authorizeUrl) {}
    public record Finish(String issuer, boolean newlyLinked) {}
    private record Pending(long owner, String verifier, String nonce) {}

    static final String CALLBACK_PATH = "/prp/me/mcp-link/callback";
    static final String CHATGPT_CLIENT_ID = "https://chatgpt.com/oauth/client.json";
    private final JdbcTemplate db;
    private final UserStore users;
    private final PasswordEncoder passwords;
    private final LoginAttemptLimiter attempts;
    private final McpClientGrantService grants;
    private final McpIdentityLinkService identities;
    private final RestTemplate rest;
    private final JwtDecoder idTokenDecoder;
    private final String issuer;
    private final String firstPartyClient;
    private final String redirectUri;
    private final String authorizationEndpoint;
    private final String tokenEndpoint;
    private final SecureRandom random = new SecureRandom();

    public McpFirstPartyOidcLinkService(
            JdbcTemplate db, UserStore users, PasswordEncoder passwords,
            LoginAttemptLimiter attempts, McpClientGrantService grants,
            McpIdentityLinkService identities, RestTemplateBuilder httpBuilder,
            @Value("${matrix-prp.mcp.oauth.enabled:false}") boolean oauthEnabled,
            @Value("${matrix-prp.mcp.oauth.issuer:}") String issuer,
            @Value("${matrix-prp.mcp.oauth.jwk-set-uri:}") String jwks,
            @Value("${matrix-prp.mcp.oauth.resource:}") String resource,
            @Value("${matrix-prp.mcp.oauth.first-party-link.client-id:}") String clientId,
            @Value("${matrix-prp.mcp.oauth.first-party-link.redirect-uri:}") String redirect) {
        if (!oauthEnabled) throw new IllegalStateException("First-party OIDC linking requires MCP OAuth");
        this.issuer = McpOAuthResourceServerConfig.strictHttps(issuer, "First-party Keycloak issuer");
        String keyUrl = McpOAuthResourceServerConfig.strictHttps(jwks, "First-party Keycloak JWKS");
        String resourceUrl = McpOAuthResourceServerConfig.strictHttps(resource, "First-party MCP resource");
        if (!"/api/mcp".equals(URI.create(resourceUrl).getRawPath()))
            throw new IllegalStateException("Canonical MCP resource path required");
        if (!keyUrl.equals(this.issuer + "/protocol/openid-connect/certs"))
            throw new IllegalStateException("First-party JWKS must be from the exact Keycloak issuer");
        if (clientId == null || !clientId.matches("[A-Za-z0-9][A-Za-z0-9._~-]{2,127}")
                || clientId.equals(CHATGPT_CLIENT_ID))
            throw new IllegalStateException("A separate fixed first-party Keycloak client ID is required");
        this.firstPartyClient = clientId;
        this.redirectUri = McpOAuthResourceServerConfig.strictHttps(
            redirect, "First-party OIDC callback");
        URI callback = URI.create(this.redirectUri);
        URI resourceRef = URI.create(resourceUrl);
        if (!callback.getHost().equals(resourceRef.getHost())
                || !CALLBACK_PATH.equals(callback.getRawPath()))
            throw new IllegalStateException("First-party callback must be exact PRP test-site path");
        authorizationEndpoint = this.issuer + "/protocol/openid-connect/auth";
        tokenEndpoint = this.issuer + "/protocol/openid-connect/token";
        this.db = db;
        this.users = users;
        this.passwords = passwords;
        this.attempts = attempts;
        this.grants = grants;
        this.identities = identities;
        this.rest = httpBuilder.connectTimeout(Duration.ofSeconds(2))
            .readTimeout(Duration.ofSeconds(5)).build();

        NimbusJwtDecoder decoder = NimbusJwtDecoder.withJwkSetUri(keyUrl)
            .jwsAlgorithm(SignatureAlgorithm.RS256).build();
        var standard = JwtValidators.createDefaultWithIssuer(this.issuer);
        decoder.setJwtValidator(jwt -> {
            var validated = standard.validate(jwt);
            if (validated.hasErrors()) return validated;
            List<String> aud = jwt.getAudience();
            if (!aud.contains(firstPartyClient)
                    || (aud.size() > 1 && !firstPartyClient.equals(jwt.getClaimAsString("azp"))))
                return OAuth2TokenValidatorResult.failure(new OAuth2Error(
                    "invalid_token", "Invalid first-party ID token audience", null));
            return OAuth2TokenValidatorResult.success();
        });
        this.idTokenDecoder = decoder;
    }

    public Begin begin(String password) {
        long owner = CurrentUser.id();
        if (!grants.grantedScopes(owner, CHATGPT_CLIENT_ID).contains("prp.tasks.read"))
            throw new ResponseStatusException(HttpStatus.FORBIDDEN,
                "Authorize ChatGPT task reading in PRP before linking");
        UserAccount account = users.findById(owner).orElse(null);
        if (account == null || !account.enabled())
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        attempts.assertAllowed("mcp-first-party-link", account.username());
        if (password == null || password.length() > 256
                || !passwords.matches(password, account.passwordHash())) {
            attempts.recordFailure("mcp-first-party-link", account.username());
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "PRP reauthentication failed");
        }
        attempts.recordSuccess("mcp-first-party-link", account.username());
        Integer count = db.queryForObject(
            "SELECT COUNT(*) FROM prp_mcp_oidc_link_flows WHERE user_id=? " +
            "AND consumed_at IS NULL AND expires_at > CURRENT_TIMESTAMP", Integer.class, owner);
        if (count != null && count >= 3)
            throw new ResponseStatusException(HttpStatus.TOO_MANY_REQUESTS,
                "Too many pending identity link requests");
        String state = randomToken(32);
        String nonce = randomToken(32);
        String verifier = randomToken(48);
        db.update("INSERT INTO prp_mcp_oidc_link_flows " +
            "(state_hash,user_id,code_verifier,oidc_nonce,expires_at) " +
            "VALUES (?,?,?,?,?)", sha256(state), owner, verifier, nonce,
            java.sql.Timestamp.valueOf(LocalDateTime.now().plusMinutes(5)));
        String challenge = Base64.getUrlEncoder().withoutPadding()
            .encodeToString(digest(verifier));
        String url = UriComponentsBuilder.fromUriString(authorizationEndpoint)
            .queryParam("response_type", "code")
            .queryParam("client_id", firstPartyClient)
            .queryParam("redirect_uri", redirectUri)
            .queryParam("scope", "openid")
            .queryParam("state", state)
            .queryParam("nonce", nonce)
            .queryParam("code_challenge", challenge)
            .queryParam("code_challenge_method", "S256")
            .build().encode().toUriString();
        return new Begin(url);
    }

    public Finish finish(String state, String code, String responseIssuer) {
        long owner = CurrentUser.id();
        if (state == null || !state.matches("[A-Za-z0-9_-]{43}")
                || code == null || code.isBlank() || code.length() > 4096
                || !issuer.equals(responseIssuer))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid OIDC response");
        List<Pending> flows = db.query(
            "SELECT user_id,code_verifier,oidc_nonce FROM prp_mcp_oidc_link_flows " +
            "WHERE state_hash=? AND user_id=? AND consumed_at IS NULL AND expires_at > CURRENT_TIMESTAMP",
            (rs, row) -> new Pending(rs.getLong(1), rs.getString(2), rs.getString(3)),
            sha256(state), owner);
        if (flows.size() != 1)
            throw new ResponseStatusException(HttpStatus.CONFLICT, "OIDC state unavailable or expired");
        // Claim first in an autocommitted statement; a failed token exchange
        // must never make the flow reusable. No transaction wraps this method.
        int consumed = db.update("UPDATE prp_mcp_oidc_link_flows " +
            "SET consumed_at=CURRENT_TIMESTAMP WHERE state_hash=? AND user_id=? " +
            "AND consumed_at IS NULL AND expires_at > CURRENT_TIMESTAMP",
            sha256(state), owner);
        if (consumed != 1)
            throw new ResponseStatusException(HttpStatus.CONFLICT, "OIDC state already consumed");
        Pending pending = flows.getFirst();
        if (!grants.grantedScopes(owner, CHATGPT_CLIENT_ID).contains("prp.tasks.read"))
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "ChatGPT task consent revoked");

        var form = new LinkedMultiValueMap<String, String>();
        form.add("grant_type", "authorization_code");
        form.add("client_id", firstPartyClient);
        form.add("code", code);
        form.add("code_verifier", pending.verifier());
        form.add("redirect_uri", redirectUri);
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_FORM_URLENCODED);
        Jwt id;
        try {
            Map<?, ?> response = rest.postForObject(
                tokenEndpoint, new HttpEntity<>(form, headers), Map.class);
            Object idToken = response == null ? null : response.get("id_token");
            if (!(idToken instanceof String rawId) || rawId.length() > 32768)
                throw new IllegalArgumentException("Invalid ID token");
            id = idTokenDecoder.decode(rawId);
        } catch (RestClientException | JwtException | IllegalArgumentException ex) {
            // Never log token endpoint response, code, state, bearer or nonce.
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED,
                "First-party Keycloak identity verification failed");
        }
        byte[] expected = pending.nonce().getBytes(StandardCharsets.US_ASCII);
        String signedNonce = id.getClaimAsString("nonce");
        if (signedNonce == null || !MessageDigest.isEqual(
                expected, signedNonce.getBytes(StandardCharsets.US_ASCII)))
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "OIDC nonce mismatch");
        String subject = id.getSubject();
        if (subject == null || subject.isBlank() || subject.length() > 255)
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Missing verified OIDC subject");
        // Separate @Transactional service enforces one-to-one mapping, subject
        // integrity and owner availability; this browser never sees tokens.
        boolean created = identities.linkFirstPartyOwner(owner, issuer, subject, CHATGPT_CLIENT_ID);
        return new Finish(issuer, created);
    }

    private String randomToken(int bytes) {
        byte[] data = new byte[bytes];
        random.nextBytes(data);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(data);
    }

    private static byte[] digest(String value) {
        try {
            return MessageDigest.getInstance("SHA-256")
                .digest(value.getBytes(StandardCharsets.US_ASCII));
        } catch (java.security.NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }

    private static String sha256(String value) {
        return HexFormat.of().formatHex(digest(value));
    }
}
