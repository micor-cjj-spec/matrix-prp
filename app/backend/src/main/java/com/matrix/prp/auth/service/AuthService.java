package com.matrix.prp.auth.service;

import com.matrix.prp.auth.model.InvitationResponse;
import com.matrix.prp.auth.model.LoginRequest;
import com.matrix.prp.auth.model.LoginResponse;
import com.matrix.prp.auth.model.RegisterRequest;
import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.auth.repository.UserStore;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.LocalDateTime;
import java.util.Base64;
import java.util.HexFormat;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class AuthService {
    private static final SecureRandom RANDOM = new SecureRandom();
    private final JwtService jwtService;
    private final UserStore users;
    private final PasswordEncoder passwords;

    public AuthService(JwtService jwtService, UserStore users, PasswordEncoder passwords) {
        this.jwtService = jwtService;
        this.users = users;
        this.passwords = passwords;
    }

    public LoginResponse login(LoginRequest request) {
        UserAccount user = users.findByUsername(request.username()).orElse(null);
        if (user == null || !user.enabled() || !passwords.matches(request.password(), user.passwordHash())) {
            throw new BadCredentialsException("Invalid username or password");
        }
        return loggedIn(user);
    }

    @Transactional
    public LoginResponse register(RegisterRequest request) {
        if (users.findByUsername(request.username()).isPresent()) {
            throw new IllegalArgumentException("Username already exists");
        }
        if (!users.consumeInvitation(hashCode(request.invitationCode()), LocalDateTime.now())) {
            throw new IllegalArgumentException("Invalid or expired invitation");
        }
        UserAccount user = users.create(request.username(), request.displayName(),
                passwords.encode(request.password()), false);
        return loggedIn(user);
    }

    public InvitationResponse issueInvitation() {
        UserProfile issuer = requireAdmin();
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        String code = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        LocalDateTime expiresAt = LocalDateTime.now().plusDays(7);
        users.addInvitation(hashCode(code), issuer.id(), expiresAt);
        return new InvitationResponse(code, expiresAt);
    }

    public UserProfile requireAdmin() {
        UserProfile user = currentUser();
        UserAccount account = users.findById(user.id()).orElseThrow(() ->
                new ResponseStatusException(HttpStatus.UNAUTHORIZED));
        if (!account.enabled() || !account.administrator()) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Admin access required");
        }
        return user;
    }

    public UserProfile currentUser() {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth != null && auth.isAuthenticated() && auth.getPrincipal() instanceof UserProfile user) {
            return user;
        }
        throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Authentication is required");
    }

    private LoginResponse loggedIn(UserAccount user) {
        return new LoginResponse(jwtService.issueToken(user.profile()), "Bearer",
                jwtService.expirationSeconds(), user.profile());
    }

    private String hashCode(String code) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(code.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (java.security.NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}

