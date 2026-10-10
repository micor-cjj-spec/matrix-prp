package com.matrix.prp.video;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

@Component
public class MediaTicketService {
    public static final long TTL_SECONDS = 7200;
    private final byte[] key;

    public MediaTicketService(@Value("${matrix-prp.security.jwt-secret}") String secret) {
        if (secret == null || secret.getBytes(StandardCharsets.UTF_8).length < 32) {
            throw new IllegalArgumentException("Media signing secret must be at least 32 bytes");
        }
        key = secret.getBytes(StandardCharsets.UTF_8).clone();
    }

    public Ticket issue(long videoId, long userId) {
        long expires = Instant.now().getEpochSecond() + TTL_SECONDS;
        String raw = videoId + ":" + userId + ":" + expires;
        String payload = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(raw.getBytes(StandardCharsets.UTF_8));
        return new Ticket(payload + "." + sign(payload), expires);
    }

    public long verify(String token, long videoId) {
        if (token == null || token.length() > 256 || !token.contains(".")) {
            throw forbidden();
        }
        String[] parts = token.split("\\.", -1);
        if (parts.length != 2 || !MessageDigest.isEqual(
                sign(parts[0]).getBytes(StandardCharsets.US_ASCII),
                parts[1].getBytes(StandardCharsets.US_ASCII))) {
            throw forbidden();
        }
        try {
            String[] fields = new String(Base64.getUrlDecoder().decode(parts[0]),
                    StandardCharsets.UTF_8).split(":", -1);
            if (fields.length != 3 || Long.parseLong(fields[0]) != videoId
                    || Long.parseLong(fields[2]) < Instant.now().getEpochSecond()) {
                throw forbidden();
            }
            long userId = Long.parseLong(fields[1]);
            if (userId <= 0) throw forbidden();
            return userId;
        } catch (IllegalArgumentException e) {
            throw forbidden();
        }
    }

    private String sign(String data) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(key, "HmacSHA256"));
            return Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(mac.doFinal(data.getBytes(StandardCharsets.US_ASCII)));
        } catch (java.security.GeneralSecurityException e) {
            throw new IllegalStateException("Cannot sign media ticket", e);
        }
    }

    private ResponseStatusException forbidden() {
        return new ResponseStatusException(HttpStatus.FORBIDDEN, "Invalid or expired playback ticket");
    }

    public record Ticket(String value, long expiresAtEpochSeconds) { }
}
