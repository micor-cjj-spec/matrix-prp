package com.matrix.prp.auth.model;

public record LoginResponse(
        String token,
        String tokenType,
        long expiresInSeconds,
        UserProfile user) {
}
