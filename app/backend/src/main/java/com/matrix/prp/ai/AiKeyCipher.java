package com.matrix.prp.ai;

import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Base64;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

/** AES-256-GCM, fresh 96-bit nonce, authenticated user+provider binding. Never persist plaintext. */
@Component
public class AiKeyCipher {
    private final String encodedMasterKey;
    private final SecureRandom random = new SecureRandom();

    public AiKeyCipher(@Value("${matrix-prp.ai.key-encryption-secret:}") String encodedMasterKey) {
        this.encodedMasterKey = encodedMasterKey;
    }
    private SecretKeySpec masterKey() {
        try {
            byte[] bytes = Base64.getDecoder().decode(encodedMasterKey);
            if (bytes.length == 32) return new SecretKeySpec(bytes, "AES");
        } catch (IllegalArgumentException ignored) { /* fail closed */ }
        throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
            "AI encryption key is not configured; contact the administrator");
    }
    private static byte[] aad(long user, String provider) {
        return (user + ":" + provider).getBytes(StandardCharsets.UTF_8);
    }
    public String encrypt(long user, String provider, String plain) {
        try {
            byte[] nonce = new byte[12];
            random.nextBytes(nonce);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, masterKey(), new GCMParameterSpec(128, nonce));
            cipher.updateAAD(aad(user, provider));
            byte[] payload = cipher.doFinal(plain.getBytes(StandardCharsets.UTF_8));
            byte[] combined = new byte[nonce.length + payload.length];
            System.arraycopy(nonce, 0, combined, 0, nonce.length);
            System.arraycopy(payload, 0, combined, nonce.length, payload.length);
            return Base64.getEncoder().encodeToString(combined);
        } catch (ResponseStatusException e) { throw e; }
        catch (Exception e) { throw new IllegalStateException("AI credential encryption failed", e); }
    }
    public String decrypt(long user, String provider, String encrypted) {
        try {
            byte[] all = Base64.getDecoder().decode(encrypted);
            if (all.length < 29) throw new IllegalArgumentException("Invalid ciphertext");
            byte[] nonce = java.util.Arrays.copyOfRange(all, 0, 12);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, masterKey(), new GCMParameterSpec(128, nonce));
            cipher.updateAAD(aad(user, provider));
            return new String(cipher.doFinal(all, 12, all.length - 12), StandardCharsets.UTF_8);
        } catch (ResponseStatusException e) { throw e; }
        catch (Exception e) { throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "AI credential unavailable"); }
    }
}
