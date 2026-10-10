package com.matrix.prp.auth.security;

// Only referenced from @Profile("test") repositories. Legacy service-level tests have no principal.
public final class TestTenant {
    private TestTenant() {}
    public static long id() {
        try {
            return CurrentUser.id();
        } catch (org.springframework.web.server.ResponseStatusException e) {
            return 1L;
        }
    }
}
