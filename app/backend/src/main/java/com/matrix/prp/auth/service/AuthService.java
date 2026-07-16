package com.matrix.prp.auth.service;

import com.matrix.prp.auth.model.LoginRequest;
import com.matrix.prp.auth.model.LoginResponse;
import com.matrix.prp.auth.model.UserProfile;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class AuthService {

    private static final UserProfile DEVELOPMENT_USER = new UserProfile(1L, "admin", "Matrix PRP");

    private final JwtService jwtService;
    private final String developmentPassword;

    public AuthService(JwtService jwtService,
            @Value("${matrix-prp.security.development-password:matrix-prp}") String developmentPassword) {
        this.jwtService = jwtService;
        this.developmentPassword = developmentPassword;
    }

    public LoginResponse login(LoginRequest request) {
        if (!DEVELOPMENT_USER.username().equals(request.username())
                || !developmentPassword.equals(request.password())) {
            throw new IllegalArgumentException("Invalid username or password");
        }

        return new LoginResponse(
                jwtService.issueToken(DEVELOPMENT_USER),
                "Bearer",
                jwtService.expirationSeconds(),
                DEVELOPMENT_USER);
    }

    public UserProfile currentUser() {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication != null && authentication.getPrincipal() instanceof UserProfile user) {
            return user;
        }
        return DEVELOPMENT_USER;
    }
}
