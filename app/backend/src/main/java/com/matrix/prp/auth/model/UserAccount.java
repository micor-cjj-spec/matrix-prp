package com.matrix.prp.auth.model;

public record UserAccount(long id, String username, String displayName, String passwordHash,
                          boolean administrator, boolean enabled) {
    public UserProfile profile() {
        return new UserProfile(id, username, displayName);
    }
}

