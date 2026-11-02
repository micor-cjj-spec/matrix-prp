package com.matrix.prp.mcp;

import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;

class McpApprovalLocationTests {
    @Test void usesConfiguredHttpsOriginAndActualFrontendBase() {
        assertThat(McpDraftService.approvalBase("https://prp-test.micor.top/api/mcp"))
            .isEqualTo("https://prp-test.micor.top/prp/");
    }
    @Test void nonOauthLocalModeRetainsCorrectRelativeFrontendBase() {
        assertThat(McpDraftService.approvalBase("")).isEqualTo("/prp/");
    }
    @Test void unsafeOriginsAreRejected() {
        for (String value : new String[]{"http://prp-test.micor.top/api/mcp",
                "https://user:password@prp-test.micor.top/api/mcp", "https://prp-test.micor.top/api/mcp?redirect=evil"}) {
            assertThatThrownBy(() -> McpDraftService.approvalBase(value)).isInstanceOf(IllegalStateException.class);
        }
    }
}
