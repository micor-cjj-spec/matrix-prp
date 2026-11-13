package com.matrix.prp.mcp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.Set;
import org.junit.jupiter.api.Test;

/** Fail-closed MCP advertisement surface, independent of token/client grants. */
class McpOAuthToolManifestTests {
    @Test
    void defaultResourceExposesOnlyTwoTaskReadTools() {
        assertThat(McpToolConfiguration.exposedNames("prp.tasks.read", false))
            .containsExactlyInAnyOrder("prp_tasks_list", "prp_task_get");
    }

    @Test
    void optInFinanceOrWellnessCannotExposeUnrelatedDataOrWrite() {
        assertThat(McpToolConfiguration.exposedNames(
            "prp.tasks.read,prp.finance.read", false))
            .containsExactlyInAnyOrder("prp_tasks_list", "prp_task_get", "prp_finance_month");
        assertThat(McpToolConfiguration.exposedNames("prp.wellness.read", false))
            .containsExactlyInAnyOrder("prp_wellness_daily", "prp_wellness_list", "prp_wellness_get", "prp_wellness_foods");
    }

    @Test
    void writeManifestRequiresIndependentFlagAndExactScope() {
        assertThatThrownBy(() -> McpToolConfiguration.exposedNames(
            "prp.tasks.read,prp.write.create", false))
            .isInstanceOf(IllegalArgumentException.class);
        assertThat(McpToolConfiguration.exposedNames(
            "prp.tasks.read,prp.write.create", true))
            .containsExactlyInAnyOrder("prp_tasks_list", "prp_task_get",
                "prp_prepare_task", "prp_prepare_finance", "prp_prepare_record")
            .doesNotContain("prp_confirm_draft", "prp_finance_month");
        assertThat(McpToolConfiguration.exposedNames("prp.write.confirm", true))
            .containsExactly("prp_confirm_draft");
    }

    @Test
    void phaseTwoReadCapabilitiesAreExplicitOptInOnly() {
        assertThat(McpToolConfiguration.exposedNames("prp.tasks.read,prp.wellness.read", false))
            .doesNotContain("prp_tasks_summary", "prp_wellness_trends", "prp_wellness_goals",
                "prp_wellness_frequent_foods", "prp_wellness_dishes");
        assertThat(McpToolConfiguration.exposedNames("prp.tasks.read", false, true))
            .containsExactlyInAnyOrder("prp_tasks_list", "prp_task_get", "prp_tasks_summary", "prp_tasks_search");
        assertThat(McpToolConfiguration.exposedNames("prp.wellness.read", false, true))
            .containsExactlyInAnyOrder("prp_wellness_daily", "prp_wellness_list",
                "prp_wellness_get", "prp_wellness_foods", "prp_wellness_trends",
                "prp_wellness_goals", "prp_wellness_frequent_foods", "prp_wellness_dishes");
    }

    @Test
    void recordReadScopeIsIsolatedAndNewToolsRemainOptIn() {
        assertThat(McpToolConfiguration.exposedNames("prp.records.read", false))
            .isEmpty();
        assertThat(McpToolConfiguration.exposedNames("prp.records.read", false, true))
            .containsExactly("prp_records_search");
        assertThat(McpToolConfiguration.exposedNames("prp.tasks.read", false, true))
            .containsExactlyInAnyOrder("prp_tasks_list", "prp_task_get",
                "prp_tasks_summary", "prp_tasks_search");
        assertThat(McpToolConfiguration.exposedNames("prp.wellness.read", false, true))
            .doesNotContain("prp_records_search", "prp_tasks_search");
    }

    @Test
    void unexpectedScopeNeverEnablesAnyMcpTool() {
        assertThatThrownBy(() -> McpToolConfiguration.exposedNames("*", true))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> McpToolConfiguration.exposedNames(
            "prp.tasks.read,prp.tasks.read", false))
            .isInstanceOf(IllegalArgumentException.class);
    }
}
