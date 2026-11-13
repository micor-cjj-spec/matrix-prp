package com.matrix.prp.mcp;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.junit.jupiter.api.Test;

/** Pure startup-configuration cases. Never open a database or MCP listener. */
class McpProductionTaskOnlyGuardTests {
    private static final String PRODUCTION_URL =
        "jdbc:mysql://127.0.0.1:3306/matrix_prp"
            + "?useUnicode=true&serverTimezone=Asia/Shanghai";

    private void allowed(String url, List<String> profiles) {
        assertThatCode(() -> McpProductionTaskOnlyGuard.verify(
            true, true, false, "prp.tasks.read", url, false, profiles))
            .doesNotThrowAnyException();
    }

    private void reject(boolean mcp, boolean oauth, boolean write, String scopes,
                        String url, boolean flyway, List<String> profiles) {
        assertThatThrownBy(() -> McpProductionTaskOnlyGuard.verify(
            mcp, oauth, write, scopes, url, flyway, profiles))
            .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void productionLoopbackOwnerDatabaseAndExactTaskScopeAllowed() {
        allowed(PRODUCTION_URL, List.of("prod"));
        allowed("jdbc:mysql://localhost/matrix_prp", List.of());
        allowed("jdbc:mysql://[::1]:3306/matrix_prp?useSSL=false", List.of("prod"));
    }

    @Test
    void deniesWriteEvenWithOnlyTaskReadAdvertised() {
        reject(true, true, true, "prp.tasks.read", PRODUCTION_URL, false,
               List.of("prod"));
    }

    @Test
    void deniesMcpWithoutOauthOrFlywayAutoupgrade() {
        reject(true, false, false, "prp.tasks.read", PRODUCTION_URL, false,
               List.of("prod"));
        reject(false, true, false, "prp.tasks.read", PRODUCTION_URL, false,
               List.of("prod"));
        reject(true, true, false, "prp.tasks.read", PRODUCTION_URL, true,
               List.of("prod"));
    }

    @Test
    void rejectsAllExtraReadAndWriteScopeConfigurations() {
        for (String scopes : List.of("prp.finance.read", "prp.wellness.read",
                "prp.tasks.read,prp.finance.read",
                "prp.tasks.read,prp.write.create", "prp.tasks.read,prp.write.confirm",
                "prp.tasks.read,prp.tasks.read", " prp.tasks.read ",
                "prp.tasks.read,", "*", "")) {
            reject(true, true, false, scopes, PRODUCTION_URL, false,
                   List.of("prod"));
        }
    }

    @Test
    void rejectsV2AndOtherNonProductionSchemas() {
        for (String url : List.of(
                "jdbc:mysql://127.0.0.1:3306/matrix_prp_mcp_v2",
                "jdbc:mysql://localhost:3306/matrix_prp_task_producer_ci",
                "jdbc:mysql://localhost:3306/matrix_prp_mcp_newdb_review",
                "jdbc:mysql://localhost:3306/matrix_prp_backup",
                "jdbc:mysql://localhost:3306/matrix_prp/",
                "jdbc:mysql://localhost:3306/matrix_prp%2fother",
                "jdbc:mysql://localhost:3306/matrix_prp/../matrix_prp")) {
            reject(true, true, false, "prp.tasks.read", url, false,
                   List.of("prod"));
        }
    }

    @Test
    void rejectsRemoteUrlsAndEmbeddedCredentials() {
        for (String url : List.of(
                "jdbc:mysql://test-host:3306/matrix_prp",
                "jdbc:mysql://db.example.com:3306/matrix_prp",
                "jdbc:mysql://localhost.evil.example:3306/matrix_prp",
                "jdbc:mysql://user:secret@127.0.0.1/matrix_prp",
                "jdbc:mysql:loadbalance://127.0.0.1:3306/matrix_prp",
                "jdbc:mysql://127.0.0.1/matrix_prp#ignored",
                "jdbc:mysql://127.0.0.1:0/matrix_prp",
                "jdbc:mysql://127.0.0.1:65536/matrix_prp")) {
            reject(true, true, false, "prp.tasks.read", url, false,
                   List.of("prod"));
        }
    }

    @Test
    void rejectsCredentialSessionAndEncodedJdbcQueryOverrides() {
        for (String suffix : List.of(
                "?user=alice", "?password=secret", "?pwd=secret",
                "?serverTimezone=UTC&user=alice",
                "?useSSL=false&password=secret",
                "?socketFactory=com.example.FakeFactory",
                "?sessionVariables=sql_mode=ANSI",
                "?serverTimezone=UTC&serverTimezone=Asia/Shanghai",
                "?us%65r=evil",
                "?serverTimezone=UTC%26password%3Dsecret",
                "?serverTimezone=UTC;",
                "?useSSL=false&",
                "?=bad")) {
            reject(true, true, false, "prp.tasks.read",
                    "jdbc:mysql://localhost:3306/matrix_prp" + suffix,
                    false, List.of("prod"));
        }
        allowed("jdbc:mysql://localhost:3306/matrix_prp"
              + "?useUnicode=true&characterEncoding=UTF-8"
              + "&connectionCollation=utf8mb4_unicode_ci"
              + "&serverTimezone=Asia/Shanghai&useSSL=false"
              + "&allowPublicKeyRetrieval=true",
              List.of("prod"));
    }

    @Test
    void testOrIntegrationProfileCannotMasqueradeAsProductionCanary() {
        reject(true, true, false, "prp.tasks.read", PRODUCTION_URL, false,
               List.of("prod", "test"));
        reject(true, true, false, "prp.tasks.read", PRODUCTION_URL, false,
               List.of("video-integration"));
    }

    @Test
    void disabledCanaryDoesNotRegisterBeanInActualSpringContext() {
        new ApplicationContextRunner()
            .withUserConfiguration(McpProductionTaskOnlyGuard.class)
            .run(ctx -> org.assertj.core.api.Assertions.assertThat(ctx)
                .doesNotHaveBean(McpProductionTaskOnlyGuard.class));
    }

    @Test
    void enabledCanaryStartsOnlyWithActualSpringTaskReadConfiguration() {
        new ApplicationContextRunner()
            .withUserConfiguration(McpProductionTaskOnlyGuard.class)
            .withPropertyValues(
                "matrix-prp.mcp.production-tasks-only=true",
                "matrix-prp.mcp.enabled=true",
                "matrix-prp.mcp.oauth.enabled=true",
                "matrix-prp.mcp.write-enabled=false",
                "matrix-prp.mcp.oauth.advertised-scopes=prp.tasks.read",
                "spring.datasource.url=jdbc:mysql://127.0.0.1:3306/matrix_prp",
                "spring.flyway.enabled=false")
            .run(ctx -> org.assertj.core.api.Assertions.assertThat(ctx)
                .hasNotFailed().hasSingleBean(McpProductionTaskOnlyGuard.class));
    }

    @Test
    void actualSpringContextFailsToStartWithProductionCanaryAndWrite() {
        new ApplicationContextRunner()
            .withUserConfiguration(McpProductionTaskOnlyGuard.class)
            .withPropertyValues(
                "matrix-prp.mcp.production-tasks-only=true",
                "matrix-prp.mcp.enabled=true",
                "matrix-prp.mcp.oauth.enabled=true",
                "matrix-prp.mcp.write-enabled=true",
                "matrix-prp.mcp.oauth.advertised-scopes=prp.tasks.read",
                "spring.datasource.url=jdbc:mysql://127.0.0.1:3306/matrix_prp",
                "spring.flyway.enabled=false")
            .run(ctx -> org.assertj.core.api.Assertions.assertThat(ctx.getStartupFailure())
                .isNotNull());
    }

    @Test
    void rejectsNullOrMissingJdbcWithoutLeakingSecrets() {
        assertThatThrownBy(() -> McpProductionTaskOnlyGuard.verify(
            true, true, false, "prp.tasks.read", null, false, List.of()))
            .isInstanceOf(IllegalStateException.class)
            .hasMessageNotContaining("jdbc:");
        assertThatThrownBy(() -> McpProductionTaskOnlyGuard.verify(
            true, true, false, "prp.tasks.read",
            "jdbc:mysql://user:my-private-password@127.0.0.1:3306/matrix_prp",
            false, List.of()))
            .isInstanceOf(IllegalStateException.class)
            .hasMessageNotContaining("my-private-password");
    }
}
