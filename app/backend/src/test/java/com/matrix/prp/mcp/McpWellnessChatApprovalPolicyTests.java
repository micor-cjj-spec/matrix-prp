package com.matrix.prp.mcp;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.wellness.WellnessService;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

/** Boundaries for the default-off ChatGPT approval path and nested optional MCP input. */
class McpWellnessChatApprovalPolicyTests {
    private static final String CHATGPT = "https://chatgpt.com/oauth/client.json";

    private UsernamePasswordAuthenticationToken auth(String client, boolean create, boolean confirm) {
        var authorities = new java.util.ArrayList<SimpleGrantedAuthority>();
        if (create) authorities.add(new SimpleGrantedAuthority("SCOPE_prp.wellness.write.create"));
        if (confirm) authorities.add(new SimpleGrantedAuthority("SCOPE_prp.wellness.write.confirm"));
        var result = new UsernamePasswordAuthenticationToken("verified-owner", null, authorities);
        result.setDetails(new McpScopeGuard.VerifiedClient(client,
                Set.of("prp.wellness.write.create", "prp.wellness.write.confirm")));
        return result;
    }

    @Test void chatConfirmationIsExplicitOptInOnlyForExactChatgptWellnessCreate() {
        var good = auth(CHATGPT, true, true);
        assertThat(McpDraftService.chatApprovalEligible(true, "WELLNESS_CREATE", "PENDING", good)).isTrue();
        assertThat(McpDraftService.chatApprovalEligible(false, "WELLNESS_CREATE", "PENDING", good)).isFalse();
        for (String kind : List.of("WELLNESS_UPDATE", "WELLNESS_DELETE", "TASK", "FINANCE", "RECORD")) {
            assertThat(McpDraftService.chatApprovalEligible(true, kind, "PENDING", good)).isFalse();
        }
        assertThat(McpDraftService.chatApprovalEligible(true, "WELLNESS_CREATE", "APPROVED", good)).isFalse();
        assertThat(McpDraftService.chatApprovalEligible(true, "WELLNESS_CREATE", "PENDING",
                auth("another-client", true, true))).isFalse();
        assertThat(McpDraftService.chatApprovalEligible(true, "WELLNESS_CREATE", "PENDING",
                auth(CHATGPT, true, false))).isFalse();
        assertThat(McpDraftService.chatApprovalEligible(true, "WELLNESS_CREATE", "PENDING",
                auth(CHATGPT, false, true))).isFalse();
        assertThat(McpDraftService.chatApprovalEligible(true, "WELLNESS_CREATE", "PENDING", null)).isFalse();
    }

    @Test void catalogAndEstimateFoodInputsCanOmitMutuallyExclusiveFields() {
        var mapper = new ObjectMapper().findAndRegisterModules();
        var support = new McpWellnessSupport(
            mock(JdbcTemplate.class), mock(WellnessService.class), mapper,
            jakarta.validation.Validation.buildDefaultValidatorFactory().getValidator());

        var catalog = support.fromMcpInput("meal", Map.of("meal", Map.of(
            "mealDate", "2026-11-12", "mealType", "BREAKFAST",
            "items", List.of(Map.of("foodId", 2, "grams", 100)))));
        assertThat(catalog.meal().items().getFirst().foodId()).isEqualTo(2L);
        assertThat(catalog.meal().items().getFirst().name()).isNull();
        assertThat(catalog.meal().items().getFirst().calories()).isNull();

        var estimate = support.fromMcpInput("meal", Map.of("meal", Map.of(
            "mealDate", "2026-11-12", "mealType", "BREAKFAST",
            "items", List.of(Map.of("name", "Two cooked eggs", "grams", 100, "calories", 144)))));
        assertThat(estimate.meal().items().getFirst().foodId()).isNull();
        assertThat(estimate.meal().items().getFirst().calories()).isEqualByComparingTo("144");

        assertThatThrownBy(() -> support.fromMcpInput("meal",
            Map.of("meal", Map.of(), "metric", Map.of())))
            .isInstanceOf(org.springframework.web.server.ResponseStatusException.class);
        assertThatThrownBy(() -> support.fromMcpInput("meal", Map.of("metric", Map.of())))
            .isInstanceOf(org.springframework.web.server.ResponseStatusException.class);
    }
}
