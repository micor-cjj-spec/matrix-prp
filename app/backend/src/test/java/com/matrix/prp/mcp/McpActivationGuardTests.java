package com.matrix.prp.mcp;

import java.util.List;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class McpActivationGuardTests {
    @Test
    void allDisabledIsAllowed() {
        assertThatCode(() -> McpActivationGuard.verify(false, false, false, List.of()))
            .doesNotThrowAnyException();
    }

    @Test
    void oauthProtectedMcpIsAllowedWithoutExposingWrites() {
        assertThatCode(() -> McpActivationGuard.verify(true, true, false, List.of("dev")))
            .doesNotThrowAnyException();
    }

    @Test
    void oauthProtectedWritesRequireBothSwitches() {
        assertThatCode(() -> McpActivationGuard.verify(true, true, true, List.of()))
            .doesNotThrowAnyException();
        assertThatThrownBy(() -> McpActivationGuard.verify(false, true, false, List.of()))
            .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> McpActivationGuard.verify(false, false, true, List.of()))
            .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void rejectsLegacyJwtOnlyMcpInNonTestRuntime() {
        for (var profiles : List.of(List.<String>of(), List.of("dev"), List.of("prod"))) {
            assertThatThrownBy(() -> McpActivationGuard.verify(true, false, false, profiles))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("requires OAuth");
        }
    }

    @Test
    void temporaryLegacyTransportAllowedOnlyByExplicitTestProfiles() {
        assertThatCode(() -> McpActivationGuard.verify(true, false, false, List.of("test")))
            .doesNotThrowAnyException();
        assertThatCode(() -> McpActivationGuard.verify(true, false, true, List.of("video-integration")))
            .doesNotThrowAnyException();
    }
}
