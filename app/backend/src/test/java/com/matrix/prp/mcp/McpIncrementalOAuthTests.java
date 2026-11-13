package com.matrix.prp.mcp;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.sql.ResultSet;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.RowMapper;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/** Actual servlet security chain, actual SDK tool registry and result serialization. */
class McpIncrementalOAuthTests extends McpExpandedCapabilitiesTests {
    private final ObjectMapper json = new ObjectMapper();
    private static final String RESOURCE_METADATA = "https://micor.top/.well-known/oauth-protected-resource/api/mcp";

    private JsonNode result(String body) throws Exception {
        var r = request(body);
        assertThat(r.getResponse().getStatus()).isEqualTo(200);
        return json.readTree(r.getResponse().getContentAsString()).path("result");
    }
    @Test void everyToolDeclaresItsExactOAuthScopeAndPreservesReadOnlyAnnotations() throws Exception {
        JsonNode tools = result("{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\"}").path("tools");
        Map<String,String> expected = Map.ofEntries(
            Map.entry("prp_tasks_list","prp.tasks.read"), Map.entry("prp_task_get","prp.tasks.read"),
            Map.entry("prp_finance_month","prp.finance.read"), Map.entry("prp_wellness_daily","prp.wellness.read"),
            Map.entry("prp_prepare_task","prp.write.create"), Map.entry("prp_prepare_finance","prp.write.create"),
            Map.entry("prp_prepare_record","prp.write.create"), Map.entry("prp_prepare_task_update","prp.write.update"),
            Map.entry("prp_prepare_task_status","prp.write.update"),
            Map.entry("prp_prepare_task_delete","prp.write.delete"), Map.entry("prp_draft_status","prp.write.status"),
            Map.entry("prp_confirm_draft","prp.write.confirm"),
            Map.entry("prp_wellness_list","prp.wellness.read"),Map.entry("prp_wellness_get","prp.wellness.read"),Map.entry("prp_wellness_foods","prp.wellness.read"));
        assertThat(tools.size()).isEqualTo(expected.size());
        for (JsonNode tool : tools) {
            String name=tool.path("name").asText(); JsonNode schemes=tool.path("_meta").path("securitySchemes");
            assertThat(schemes.size()).isEqualTo(1);
            assertThat(schemes.get(0).path("type").asText()).isEqualTo("oauth2");
            assertThat(schemes.get(0).path("scopes").size()).isEqualTo(1);
            assertThat(schemes.get(0).path("scopes").get(0).asText()).isEqualTo(expected.get(name));
            if (name.equals("prp_tasks_list")) {
                assertThat(tool.path("annotations").path("readOnlyHint").asBoolean()).isTrue();
                assertThat(tool.path("annotations").path("destructiveHint").asBoolean()).isFalse();
            }
        }
        verifyNoInteractions(jdbc);
    }
    @Test void oldReadOnlyTokenGetsExactScopeChallengeWithoutCreatingAnyDraft() throws Exception {
        identity(2,CLIENT,"prp.tasks.read"); JsonNode r=result(prepare());
        assertThat(r.path("isError").asBoolean()).isTrue();
        String challenge=r.path("_meta").path("mcp/www_authenticate").get(0).asText();
        assertThat(challenge).contains("Bearer ","resource_metadata=\""+RESOURCE_METADATA+"\"",
            "error=\"insufficient_scope\"","error_description=\"","scope=\"prp.write.create\"")
            .doesNotContain("expanded-test","offline_access","prp.write.delete");
        verifyNoInteractions(jdbc);
    }
    @Test void newWriteTokenCanPrepareOnlyAnOwnerBoundDraft() throws Exception {
        when(jdbc.queryForObject(anyString(),eq(Integer.class),eq(2L))).thenReturn(0);
        JsonNode r=result(prepare());assertThat(r.path("isError").asBoolean()).isFalse();
        assertThat(r.path("_meta").has("mcp/www_authenticate")).isFalse();
        assertThat(r.toString()).contains("draftId","Synthetic expanded draft");
        verify(jdbc).update(startsWith("INSERT INTO prp_mcp_write_drafts"),any(),eq(2L),eq("TASK"),any(),any());
    }
    @Test void revokedOwnerGrantRejectsEvenAStillValidWriteToken() throws Exception {
        when(grants.grantedScopes(2,CLIENT)).thenReturn(Set.of());
        assertThat(request(prepare()).getResponse().getStatus()).isEqualTo(401);verifyNoInteractions(jdbc);
    }
    @Test void missingPrpConsentIsNotMisrepresentedAsAnOAuthOnlyScopeUpgrade() throws Exception {
        when(grants.grantedScopes(2,CLIENT)).thenReturn(Set.of("prp.tasks.read"));
        JsonNode r=result(prepare());assertThat(r.path("isError").asBoolean()).isTrue();
        assertThat(r.path("_meta").has("mcp/www_authenticate")).isFalse();verifyNoInteractions(jdbc);
    }
    @Test void anotherOwnerStillGetsNoUpgradeChallengeAndCannotWrite() throws Exception {
        identity(1,CLIENT,SCOPES);JsonNode r=result(prepare());assertThat(r.path("isError").asBoolean()).isTrue();
        assertThat(r.path("_meta").has("mcp/www_authenticate")).isFalse();verifyNoInteractions(jdbc);
    }
    @Test void anotherClientStillGetsNoUpgradeChallengeAndCannotWrite() throws Exception {
        identity(2,"unreviewed-client",SCOPES);JsonNode r=result(prepare());assertThat(r.path("isError").asBoolean()).isTrue();
        assertThat(r.path("_meta").has("mcp/www_authenticate")).isFalse();verifyNoInteractions(jdbc);
    }
    @Test void consentRevokedBetweenAuthenticationAndInvocationCannotCreateDraft() throws Exception {
        when(grants.grantedScopes(2,CLIENT)).thenReturn(Set.of(SCOPES.split(" "))).thenReturn(Set.of());
        JsonNode r=result(prepare());assertThat(r.path("isError").asBoolean()).isTrue();
        assertThat(r.path("_meta").has("mcp/www_authenticate")).isFalse();verifyNoInteractions(jdbc);
    }
    @Test @SuppressWarnings("unchecked")
    void confirmChallengesForExactDraftOperationRatherThanAllWriteScopes() throws Exception {
        String id="41abc027-d67e-4bdf-8985-e3ec97d23204";
        identity(2,CLIENT,"prp.tasks.read prp.write.confirm");
        when(jdbc.query(startsWith("SELECT kind,payload_json,status,expires_at"),any(RowMapper.class),eq(id),eq(2L)))
            .thenAnswer(inv -> {
                RowMapper<Object> mapper=inv.getArgument(1);ResultSet rs=mock(ResultSet.class);
                when(rs.getString("kind")).thenReturn("TASK_DELETE");when(rs.getString("payload_json")).thenReturn("{}");
                when(rs.getString("status")).thenReturn("APPROVED");
                when(rs.getTimestamp("expires_at")).thenReturn(Timestamp.valueOf(LocalDateTime.now().plusMinutes(5)));
                return List.of(mapper.mapRow(rs,0));
            });
        JsonNode r=result("{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"prp_confirm_draft\",\"arguments\":{\"draftId\":\""+id+"\"}}}");
        assertThat(r.path("isError").asBoolean()).isTrue();
        assertThat(r.path("_meta").path("mcp/www_authenticate").get(0).asText())
            .contains("scope=\"prp.write.delete\"").doesNotContain("prp.write.update");
        verify(jdbc,never()).update(anyString(),any(Object[].class));
    }
}
