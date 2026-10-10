package com.matrix.prp.auth.model;

public record UserProfile(long id, String username, String displayName, boolean administrator) {
    public UserProfile(long id, String username, String displayName) {
        this(id, username, displayName, false);
    }
}
