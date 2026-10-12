package com.matrix.prp.auth.security;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

/** Bounded single-process login throttle. Does not trust spoofed forwarding headers. */
@Component
public final class LoginAttemptLimiter {
    private static final int MAX_KEYS = 20_000;
    private final Map<String, Window> windows = new ConcurrentHashMap<>();
    private final Clock clock;
    private final int maxFailures;
    private final Duration period;
    private final boolean enabled;

    public LoginAttemptLimiter(
            @Value("${matrix-prp.security.login-max-failures:8}") int maxFailures,
            @Value("${matrix-prp.security.login-window-minutes:10}") int windowMinutes,
            @Value("${matrix-prp.security.login-rate-limit-enabled:true}") boolean enabled) {
        this(maxFailures, Duration.ofMinutes(windowMinutes), Clock.systemUTC(), enabled);
    }

    LoginAttemptLimiter(int maxFailures, Duration period, Clock clock, boolean enabled) {
        if (maxFailures < 1 || period.isZero() || period.isNegative()) {
            throw new IllegalArgumentException("Invalid login limiter settings");
        }
        this.maxFailures = maxFailures;
        this.period = period;
        this.clock = clock;
        this.enabled = enabled;
    }

    public void assertAllowed(String peer, String username) {
        if (!enabled) return;
        String key = key(peer, username);
        Instant now = clock.instant();
        Window current = windows.get(key);
        if (current != null && now.isBefore(current.until()) && current.failures() >= maxFailures) {
            throw new ResponseStatusException(HttpStatus.TOO_MANY_REQUESTS, "Too many login attempts; try later");
        }
        if (!windows.containsKey(key) && windows.size() >= MAX_KEYS) {
            windows.entrySet().removeIf(e -> !now.isBefore(e.getValue().until()));
            if (windows.size() >= MAX_KEYS) {
                throw new ResponseStatusException(HttpStatus.TOO_MANY_REQUESTS, "Login temporarily busy");
            }
        }
    }

    public void recordFailure(String peer, String username) {
        if (!enabled) return;
        Instant now = clock.instant();
        windows.compute(key(peer, username), (k, prior) -> {
            if (prior == null || !now.isBefore(prior.until())) return new Window(1, now.plus(period));
            return new Window(prior.failures() + 1, prior.until());
        });
    }

    public void recordSuccess(String peer, String username) {
        if (enabled) windows.remove(key(peer, username));
    }

    private String key(String peer, String username) {
        return (peer == null ? "unknown" : peer) + "|" +
                (username == null ? "" : username.trim().toLowerCase(Locale.ROOT));
    }

    private record Window(int failures, Instant until) {}
}
