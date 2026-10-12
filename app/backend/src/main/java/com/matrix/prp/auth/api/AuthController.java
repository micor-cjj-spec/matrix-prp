package com.matrix.prp.auth.api;

import com.matrix.prp.auth.model.InvitationResponse;
import com.matrix.prp.auth.model.LoginRequest;
import com.matrix.prp.auth.model.LoginResponse;
import com.matrix.prp.auth.model.RegisterRequest;
import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.auth.service.AuthService;
import com.matrix.prp.common.api.ApiResponse;
import jakarta.validation.Valid;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import com.matrix.prp.auth.security.LoginAttemptLimiter;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class AuthController {
    private final AuthService authService;
    private final LoginAttemptLimiter limiter;

    public AuthController(AuthService authService, LoginAttemptLimiter limiter) {
        this.authService = authService;
        this.limiter = limiter;
    }

    @PostMapping("/auth/login")
    public ApiResponse<LoginResponse> login(@Valid @RequestBody LoginRequest request,
                                            HttpServletRequest httpRequest, HttpServletResponse response) {
        response.setHeader("Cache-Control", "no-store");
        String peer = httpRequest.getRemoteAddr();
        limiter.assertAllowed(peer, request.username());
        try {
            LoginResponse login = authService.login(request);
            limiter.recordSuccess(peer, request.username());
            return ApiResponse.success(login);
        } catch (BadCredentialsException ex) {
            limiter.recordFailure(peer, request.username());
            throw ex;
        }
    }

    @PostMapping("/auth/register")
    public ApiResponse<LoginResponse> register(@Valid @RequestBody RegisterRequest request,
                                               HttpServletResponse response) {
        response.setHeader("Cache-Control", "no-store");
        return ApiResponse.success(authService.register(request));
    }

    @PostMapping("/auth/invitations")
    public ApiResponse<InvitationResponse> issueInvitation() {
        return ApiResponse.success(authService.issueInvitation());
    }

    @GetMapping("/users/me")
    public ApiResponse<UserProfile> me() {
        return ApiResponse.success(authService.currentUser());
    }
}

