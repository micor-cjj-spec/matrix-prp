package com.matrix.prp.auth.model;

public record UserProfile(
        long id,
        String username,
        String displayName) {
}
