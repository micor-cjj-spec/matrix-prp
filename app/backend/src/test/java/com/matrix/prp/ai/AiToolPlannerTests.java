package com.matrix.prp.ai;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;

class AiToolPlannerTests {
    private final ObjectMapper json = new ObjectMapper();
    private final AiToolPlanner planner = new AiToolPlanner(json);

    @Test void parsesOnlyProviderDeclaredFunctions() throws Exception {
        var payload=json.readTree("""
            {"choices":[{"message":{"tool_calls":[
              {"type":"function","function":{"name":"tasks_list","arguments":"{\\"status\\":\\"todo\\"}"}},
              {"type":"function","function":{"name":"navigation_open","arguments":"{\\"module\\":\\"tasks\\"}"}}
            ]}}]}
            """);
        var calls=planner.parse(payload,false);
        assertThat(calls).hasSize(2);
        assertThat(calls.get(0).name()).isEqualTo("tasks_list");
        assertThat(calls.get(0).arguments().path("status").asText()).isEqualTo("todo");
        assertThat(calls.get(1).arguments().path("module").asText()).isEqualTo("tasks");
    }

    @Test void parsesAnthropicToolUseAndRejectsMalformedParameters() throws Exception {
        var payload=json.readTree("""
            {"content":[{"type":"text","text":"I'll check."},
              {"type":"tool_use","name":"finance_monthly","input":{"month":"2026-10"}}]}
            """);
        assertThat(planner.parse(payload,true)).hasSize(1);
        assertThat(planner.parse(payload,true).getFirst().arguments().path("month").asText())
            .isEqualTo("2026-10");
        var malformed=json.readTree("""
            {"choices":[{"message":{"tool_calls":[
              {"type":"function","function":{"name":"tasks_list","arguments":"not-json"}}
            ]}}]}
            """);
        assertThatThrownBy(()->planner.parse(malformed,false)).isInstanceOf(Exception.class);
    }
}
