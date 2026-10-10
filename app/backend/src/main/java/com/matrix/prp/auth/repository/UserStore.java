package com.matrix.prp.auth.repository;

import com.matrix.prp.auth.model.UserAccount;
import java.time.LocalDateTime;
import java.util.Optional;

public interface UserStore {
    Optional<UserAccount> findByUsername(String username);
    Optional<UserAccount> findById(long id);
    long countUsers();
    UserAccount create(String username, String displayName, String passwordHash, boolean administrator);
    void addInvitation(String codeHash, long issuerUserId, LocalDateTime expiresAt);
    boolean consumeInvitation(String codeHash, LocalDateTime now);
}

