package com.matrix.prp.auth.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

class LoginAttemptLimiterTests {
    private LoginAttemptLimiter limiter() {
        return new LoginAttemptLimiter(3, Duration.ofMinutes(10),
                Clock.fixed(Instant.parse("2026-10-12T00:00:00Z"), ZoneOffset.UTC), true);
    }

    @Test
    void limitsFailedAttemptsAndSeparatesSources() {
        LoginAttemptLimiter guard = limiter();
        for (int i = 0; i < 3; i++) {
            guard.assertAllowed("192.0.2.1", "Alice");
            guard.recordFailure("192.0.2.1", "Alice");
        }
        assertThatThrownBy(() -> guard.assertAllowed("192.0.2.1", "alice"))
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(e -> assertThat(((ResponseStatusException) e).getStatusCode())
                        .isEqualTo(HttpStatus.TOO_MANY_REQUESTS));
        assertThatCode(() -> guard.assertAllowed("192.0.2.2", "alice")).doesNotThrowAnyException();
        assertThatCode(() -> guard.assertAllowed("192.0.2.1", "bob")).doesNotThrowAnyException();
    }

    @Test
    void successResetsCounterAndDisabledModeDoesNotBlock() {
        LoginAttemptLimiter guard = limiter();
        for (int i = 0; i < 3; i++) guard.recordFailure("192.0.2.3", "alice");
        guard.recordSuccess("192.0.2.3", "alice");
        assertThatCode(() -> guard.assertAllowed("192.0.2.3", "alice")).doesNotThrowAnyException();
        LoginAttemptLimiter disabled = new LoginAttemptLimiter(1, Duration.ofMinutes(1),
                Clock.systemUTC(), false);
        disabled.recordFailure("192.0.2.3", "alice");
        assertThatCode(() -> disabled.assertAllowed("192.0.2.3", "alice")).doesNotThrowAnyException();
    }
}
