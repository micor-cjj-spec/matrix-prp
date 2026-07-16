package com.matrix.prp.auth.service;

import com.matrix.prp.auth.model.UserProfile;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;
import javax.crypto.SecretKey;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class JwtService {

    private final SecretKey secretKey;
    private final long expirationMinutes;

    public JwtService(
            @Value("${matrix-prp.security.jwt-secret}") String secret,
            @Value("${matrix-prp.security.jwt-expiration-minutes:1440}") long expirationMinutes) {
        this.secretKey = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
        this.expirationMinutes = expirationMinutes;
    }

    public String issueToken(UserProfile user) {
        Instant now = Instant.now();
        Instant expiresAt = now.plusSeconds(expirationSeconds());
        return Jwts.builder()
                .subject(user.username())
                .claim("uid", user.id())
                .claim("displayName", user.displayName())
                .issuedAt(Date.from(now))
                .expiration(Date.from(expiresAt))
                .signWith(secretKey)
                .compact();
    }

    public UserProfile parseToken(String token) {
        Claims claims = Jwts.parser()
                .verifyWith(secretKey)
                .build()
                .parseSignedClaims(token)
                .getPayload();
        Number userId = claims.get("uid", Number.class);
        String displayName = claims.get("displayName", String.class);
        return new UserProfile(userId.longValue(), claims.getSubject(), displayName);
    }

    public long expirationSeconds() {
        return expirationMinutes * 60;
    }
}
