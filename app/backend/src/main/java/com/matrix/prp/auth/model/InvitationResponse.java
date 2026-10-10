package com.matrix.prp.auth.model;

import java.time.LocalDateTime;

public record InvitationResponse(String code, LocalDateTime expiresAt) {
}

