package com.matrix.prp.auth.service;

import com.matrix.prp.auth.repository.UserStore;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

@Component
@Profile("!test")
public class AdminBootstrap implements ApplicationRunner {
    private final UserStore users;
    private final PasswordEncoder encoder;
    private final String username;
    private final String password;

    public AdminBootstrap(UserStore users, PasswordEncoder encoder,
            @Value("${matrix-prp.bootstrap.username:}") String username,
            @Value("${matrix-prp.bootstrap.password:}") String password) {
        this.users = users;
        this.encoder = encoder;
        this.username = username;
        this.password = password;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (users.countUsers() != 0) {
            return;
        }
        if (!username.matches("[a-zA-Z0-9_]{3,32}") || password.length() < 12) {
            throw new IllegalStateException("Set a strong bootstrap username and password before first startup");
        }
        users.create(username, username, encoder.encode(password), true);
    }
}

