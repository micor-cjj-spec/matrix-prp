package com.matrix.prp.auth.api;

import com.matrix.prp.auth.model.LoginRequest;
import com.matrix.prp.auth.model.LoginResponse;
import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.auth.service.AuthService;
import com.matrix.prp.common.api.ApiResponse;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class AuthController {

    private final AuthService authService;

    public AuthController(AuthService authService) {
        this.authService = authService;
    }

    @PostMapping("/auth/login")
    public ApiResponse<LoginResponse> login(@Valid @RequestBody LoginRequest request) {
        return ApiResponse.success(authService.login(request));
    }

    @GetMapping("/users/me")
    public ApiResponse<UserProfile> me() {
        return ApiResponse.success(authService.currentUser());
    }
}
