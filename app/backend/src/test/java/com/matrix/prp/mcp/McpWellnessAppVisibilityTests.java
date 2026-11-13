package com.matrix.prp.mcp;

import com.matrix.prp.finance.service.FinanceService;
import com.matrix.prp.records.service.RecordService;
import com.matrix.prp.tasks.service.TaskService;
import com.matrix.prp.wellness.WellnessService;
import io.modelcontextprotocol.server.McpStatelessServerFeatures;
import io.modelcontextprotocol.spec.McpSchema;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

/** The ChatGPT approval action is never model-visible and is absent by default. */
class McpWellnessAppVisibilityTests {
    private static final String SCOPES = String.join(",", McpProductionWellnessGuard.SCOPES);

    @SuppressWarnings("unchecked")
    private List<McpStatelessServerFeatures.SyncToolSpecification> specs(boolean uiEnabled) {
        var drafts = mock(McpDraftService.class);
        var tools = new PrpMcpTools(mock(TaskService.class), mock(FinanceService.class),
            mock(WellnessService.class), mock(com.matrix.prp.records.service.RecordService.class),
            drafts, mock(McpScopeGuard.class));
        ObjectProvider<McpClientGrantService> grants = mock(ObjectProvider.class);
        when(grants.getObject()).thenReturn(mock(McpClientGrantService.class));
        return new McpToolConfiguration().prpMcpSpecifications(
            tools, mock(McpScopeGuard.class), grants, drafts,
            "https://micor.top/api/mcp", true, SCOPES, true, uiEnabled, false);
    }

    @Test void appOnlyApprovalIsAbsentWhenDisabled() {
        var tools = specs(false);
        assertThat(tools).hasSize(9);
        assertThat(tools.stream().map(x -> x.tool().name()))
            .doesNotContain("prp_chatgpt_wellness_approval");
        assertThat(tools.stream().map(x -> x.tool()))
            .allSatisfy(t -> assertThat(t.meta()).doesNotContainKey("openai/outputTemplate"));
    }

    @Test void appOnlyApprovalIsHiddenFromModelWhenUiEnabled() {
        var tools = specs(true);
        assertThat(tools).hasSize(10);
        var approval = tools.stream()
            .map(McpStatelessServerFeatures.SyncToolSpecification::tool)
            .filter(t -> "prp_chatgpt_wellness_approval".equals(t.name()))
            .findFirst().orElseThrow();
        assertThat(approval.meta()).containsKey("ui");
        assertThat(((Map<?,?>)approval.meta().get("ui")).get("visibility"))
            .isEqualTo(List.of("app"));
        assertThat(approval.annotations().destructiveHint()).isTrue();
        var create = tools.stream()
            .map(McpStatelessServerFeatures.SyncToolSpecification::tool)
            .filter(t -> "prp_prepare_wellness_create".equals(t.name()))
            .findFirst().orElseThrow();
        assertThat(((Map<?,?>)create.meta().get("ui")).get("resourceUri"))
            .isEqualTo(McpWellnessApprovalUiConfiguration.RESOURCE_URI);
        assertThat(create.meta().get("openai/outputTemplate"))
            .isEqualTo(McpWellnessApprovalUiConfiguration.RESOURCE_URI);
        var draftStatus = tools.stream()
            .map(McpStatelessServerFeatures.SyncToolSpecification::tool)
            .filter(t -> "prp_wellness_draft_status".equals(t.name()))
            .findFirst().orElseThrow();
        assertThat(draftStatus.meta().get("openai/outputTemplate"))
            .isEqualTo(McpWellnessApprovalUiConfiguration.RESOURCE_URI);
        assertThat(approval.meta()).doesNotContainKey("openai/outputTemplate");
        assertThat(tools.stream().map(x -> x.tool().name()))
            .doesNotContain("prp_prepare_finance","prp_prepare_task");
    }

    @Test void extendedReadManifestKeepsAllHealthToolsAndApprovalButNoGenericWrites() {
        var drafts = mock(McpDraftService.class);
        var tools = new PrpMcpTools(mock(TaskService.class), mock(FinanceService.class),
            mock(WellnessService.class), mock(RecordService.class), drafts, mock(McpScopeGuard.class));
        ObjectProvider<McpClientGrantService> grants = mock(ObjectProvider.class);
        when(grants.getObject()).thenReturn(mock(McpClientGrantService.class));
        String combined = SCOPES + ",prp.tasks.read,prp.records.read,prp.practice.read";
        var config = new McpToolConfiguration();
        var healthOnly = config.prpMcpSpecifications(tools,mock(McpScopeGuard.class),grants,drafts,
            "https://micor.top/api/mcp",true,SCOPES,true,true,false);
        assertThat(healthOnly).hasSize(10);
        var hidden = config.prpMcpSpecifications(tools,mock(McpScopeGuard.class),grants,drafts,
            "https://micor.top/api/mcp",true,combined,true,true,false);
        // Task list/get already predate the extra-read flag. This mixed-scope manifest
        // cannot run as production wellness-only unless the new startup guard also opts in.
        assertThat(hidden).hasSize(12);
        assertThat(hidden.stream().map(x -> x.tool().name()))
            .contains("prp_tasks_list","prp_task_get")
            .doesNotContain("prp_tasks_search","prp_records_search","prp_practice_questions");
        var extended = config.prpMcpSpecifications(tools,mock(McpScopeGuard.class),grants,drafts,
            "https://micor.top/api/mcp",true,combined,true,true,true);
        assertThat(extended).hasSize(24);
        assertThat(extended.stream().map(x -> x.tool().name())).contains(
            "prp_chatgpt_wellness_approval","prp_wellness_daily",
            "prp_tasks_summary","prp_tasks_search","prp_records_search",
            "prp_wellness_trends","prp_wellness_goals","prp_wellness_frequent_foods",
            "prp_wellness_dishes","prp_practice_subjects","prp_practice_banks",
            "prp_practice_questions","prp_practice_wrong_questions","prp_practice_statistics")
            .doesNotContain("prp_prepare_finance","prp_prepare_task","prp_prepare_task_update",
                "prp_prepare_task_delete","prp_prepare_task_status");
    }

    @Test void resourceIsASandboxedChatgptMcpAppTemplate() throws Exception {
        var resources = new McpWellnessApprovalUiConfiguration().prpChatgptApprovalResource();
        assertThat(resources).hasSize(1);
        var text = new String(getClass().getResourceAsStream("/mcp/wellness-approval.html").readAllBytes());
        assertThat(text).contains("prp_chatgpt_wellness_approval", "tools/call",
            "审批并保存", "拒绝写入", "ui/notifications/tool-result",
            "send('ui/initialize'", "protocolVersion: '2026-01-26'",
            "method:'ui/notifications/initialized'");
        assertThat(text).doesNotContain("send('initialize'", "method:'notifications/initialized'",
            "window.fetch(", "localStorage", "Authorization:");
    }
}
