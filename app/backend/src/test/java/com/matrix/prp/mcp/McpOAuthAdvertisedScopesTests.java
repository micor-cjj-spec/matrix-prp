package com.matrix.prp.mcp;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class McpOAuthAdvertisedScopesTests {
    @Test
    void taskOnlyDiscoveryDoesNotAskForOtherUsersDataCategoriesOrWrites() {
        var controller = new McpOAuthMetadataController(
            "https://prp-test.example/api/mcp", "https://auth-test.example/realms/prp-mcp",
            "prp.tasks.read", false);
        var request = new MockHttpServletRequest("GET", "/.well-known/oauth-protected-resource/api/mcp");
        var response = controller.protectedResource(request);
        assertThat(response.getBody()).containsEntry("scopes_supported", List.of("prp.tasks.read"));
        assertThat(response.getBody()).containsEntry("resource", "https://prp-test.example/api/mcp");
    }

    @Test
    void otherReadCategoriesRequireExplicitConfiguration() {
        assertThat(McpOAuthMetadataController.parseAdvertisedScopes("prp.tasks.read, prp.finance.read", false))
            .containsExactly("prp.tasks.read", "prp.finance.read");
    }

    @Test
    void invalidConfigurationCannotSilentlyAddOrDropPermissions() {
        for (String value : List.of("", " ", "*", "openid", "offline_access", "prp.tasks.read,",
                "prp.tasks.read,prp.tasks.read", "prp.tasks.read prp.finance.read", "prp.unknown")) {
            assertThatThrownBy(() -> McpOAuthMetadataController.parseAdvertisedScopes(value, false))
                .isInstanceOf(IllegalArgumentException.class);
        }
    }

    @Test
    void explicitWritesStillRequireTheIndependentWriteSwitch() {
        assertThatThrownBy(() -> McpOAuthMetadataController.parseAdvertisedScopes(
            "prp.tasks.read,prp.write.create", false)).isInstanceOf(IllegalArgumentException.class);
        assertThat(McpOAuthMetadataController.parseAdvertisedScopes("prp.tasks.read,prp.write.create", true))
            .containsExactly("prp.tasks.read", "prp.write.create");
    }
}
