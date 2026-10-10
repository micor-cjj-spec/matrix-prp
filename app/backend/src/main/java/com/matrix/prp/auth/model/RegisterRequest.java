package com.matrix.prp.auth.model;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record RegisterRequest(
        @NotBlank @Pattern(regexp = "^[a-zA-Z0-9_]{3,32}$") String username,
        @NotBlank @Size(min = 12, max = 128) String password,
        @NotBlank @Size(max = 100) String displayName,
        @NotBlank String invitationCode) {
}

