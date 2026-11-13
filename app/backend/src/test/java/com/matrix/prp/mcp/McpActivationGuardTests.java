package com.matrix.prp.mcp;

import java.util.List;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class McpActivationGuardTests {
    @Test
    void extensionFailsClosedUnlessHealthOAuthWritesAndReadOptInAreEnabled() {
        assertThatCode(() -> McpActivationGuard.verify(true,true,true,List.of("prod"),true,true,true))
            .doesNotThrowAnyException();
        for (var flags : List.of(
            List.of(false,true,true,true,true),
            List.of(true,false,true,true,true),
            List.of(true,true,false,true,true),
            List.of(true,true,true,false,true),
            List.of(true,true,true,true,false))) {
            assertThatThrownBy(() -> McpActivationGuard.verify(flags.get(0),flags.get(1),
                flags.get(2),List.of("prod"),flags.get(3),true,flags.get(4)))
                .isInstanceOf(IllegalStateException.class);
        }
    }

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
