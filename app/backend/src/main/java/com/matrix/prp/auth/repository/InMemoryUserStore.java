package com.matrix.prp.auth.repository;

import com.matrix.prp.auth.model.UserAccount;
import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.context.annotation.Profile;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Repository;

@Repository
@Profile("test")
public class InMemoryUserStore implements UserStore {
    private final Map<Long, UserAccount> users = new HashMap<>();
    private final Map<String, LocalDateTime> invitations = new HashMap<>();
    private final AtomicLong ids = new AtomicLong(1);

    public InMemoryUserStore(PasswordEncoder encoder) {
        users.put(1L, new UserAccount(1, "admin", "Matrix PRP",
                encoder.encode("matrix-prp"), true, true));
    }

    @Override
    public synchronized Optional<UserAccount> findByUsername(String username) {
        return users.values().stream().filter(u -> u.username().equals(username)).findFirst();
    }

    @Override
    public synchronized Optional<UserAccount> findById(long id) {
        return Optional.ofNullable(users.get(id));
    }

    @Override
    public synchronized long countUsers() {
        return users.size();
    }

    @Override
    public synchronized UserAccount create(String username, String displayName, String passwordHash, boolean administrator) {
        if (findByUsername(username).isPresent()) {
            throw new IllegalArgumentException("Username already exists");
        }
        long id = ids.incrementAndGet();
        UserAccount user = new UserAccount(id, username, displayName, passwordHash, administrator, true);
        users.put(id, user);
        return user;
    }

    @Override
    public synchronized void addInvitation(String hash, long issuerId, LocalDateTime expiresAt) {
        invitations.put(hash, expiresAt);
    }

    @Override
    public synchronized boolean consumeInvitation(String hash, LocalDateTime now) {
        LocalDateTime expiry = invitations.get(hash);
        if (expiry == null || !expiry.isAfter(now)) {
            return false;
        }
        invitations.remove(hash);
        return true;
    }
}

