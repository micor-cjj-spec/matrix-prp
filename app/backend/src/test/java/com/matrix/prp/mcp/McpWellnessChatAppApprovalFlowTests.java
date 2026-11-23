package com.matrix.prp.mcp;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.finance.service.FinanceService;
import com.matrix.prp.records.service.RecordService;
import com.matrix.prp.tasks.service.TaskService;
import jakarta.validation.Validation;
import java.sql.ResultSet;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.server.ResponseStatusException;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/** Regression: an ordinary MCP confirm can NEVER consume a pending draft. */
class McpWellnessChatAppApprovalFlowTests {
    private static final String ID = "2eac5bb3-2ab2-456e-81e6-939c14d25f88";
    private static final String CLIENT = "https://chatgpt.com/oauth/client.json";
    private final JdbcTemplate db = mock(JdbcTemplate.class);

    @AfterEach void clearAuth() { SecurityContextHolder.clearContext(); }

    private void auth(String client) {
        var user = new UserProfile(2L, "owner", "Owner");
        var claims = List.of(
            new SimpleGrantedAuthority("SCOPE_prp.wellness.write.create"),
            new SimpleGrantedAuthority("SCOPE_prp.wellness.write.confirm"));
        var result = new UsernamePasswordAuthenticationToken(user, null, claims);
        result.setDetails(new McpScopeGuard.VerifiedClient(client,
            Set.of("prp.wellness.write.create", "prp.wellness.write.confirm")));
        SecurityContextHolder.getContext().setAuthentication(result);
    }

    private McpDraftService drafts(boolean enabled) {
        return drafts(enabled, "https://micor.top/api/mcp");
    }

    private McpDraftService drafts(boolean enabled, String resource) {
        var d = new McpDraftService(db, new ObjectMapper().findAndRegisterModules(),
            Validation.buildDefaultValidatorFactory().getValidator(),
            mock(TaskService.class), mock(FinanceService.class), mock(RecordService.class),
            mock(UserStore.class), mock(PasswordEncoder.class), true,
            resource);
        ReflectionTestUtils.setField(d, "chatgptApprovalUiEnabled", enabled);
        return d;
    }

    @SuppressWarnings("unchecked")
    private void stubPendingApprovalQuery(String kind, String status, boolean expired, String entity) throws Exception {
        when(db.query(startsWith("SELECT kind,status,expires_at,payload_json FROM prp_mcp_write_drafts"),
                any(RowMapper.class), eq(ID), eq(2L))).thenAnswer(call -> {
            RowMapper<?> mapper = call.getArgument(1);
            ResultSet rs = mock(ResultSet.class);
            when(rs.getString("kind")).thenReturn(kind);
            when(rs.getString("status")).thenReturn(status);
            when(rs.getString("payload_json")).thenReturn("{\"entity\":\"" + entity + "\"}");
            when(rs.getTimestamp("expires_at")).thenReturn(Timestamp.valueOf(
                expired ? LocalDateTime.now().minusMinutes(1) : LocalDateTime.now().plusMinutes(10)));
            return List.of(mapper.mapRow(rs, 0));
        });
    }

    @SuppressWarnings("unchecked")
    private void stubPendingConfirmQuery(String kind) throws Exception {
        when(db.query(startsWith("SELECT kind,payload_json,result_json,status,expires_at FROM"),
                any(RowMapper.class), eq(ID), eq(2L))).thenAnswer(call -> {
            RowMapper<?> mapper = call.getArgument(1);
            ResultSet rs = mock(ResultSet.class);
            when(rs.getString("kind")).thenReturn(kind);
            when(rs.getString("status")).thenReturn("PENDING");
            when(rs.getTimestamp("expires_at")).thenReturn(Timestamp.valueOf(
                LocalDateTime.now().plusMinutes(10)));
            return List.of(mapper.mapRow(rs, 0));
        });
    }

    @Test void regularConfirmNeverConsumesPendingEvenWithUiFlagEnabled() throws Exception {
        auth(CLIENT);
        stubPendingConfirmQuery("WELLNESS_CREATE");
        assertThatThrownBy(() -> drafts(true).confirm(ID))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(ex -> assertThat(((ResponseStatusException) ex).getStatusCode())
                .isEqualTo(HttpStatus.CONFLICT));
        verify(db, never()).update(startsWith("UPDATE prp_mcp_write_drafts SET status='CONSUMED'"),
            any(), any(), any());
    }

    @Test void appOnlyActionRequiresExactClientAndExplicitFeatureFlag() throws Exception {
        stubPendingApprovalQuery("WELLNESS_CREATE", "PENDING", false, "meal");
        auth("unreviewed-client");
        assertThatThrownBy(() -> drafts(true).approveFromChatgptUi(ID, "approve"))
            .isInstanceOf(ResponseStatusException.class);
        auth(CLIENT);
        assertThatThrownBy(() -> drafts(false).approveFromChatgptUi(ID, "approve"))
            .isInstanceOf(ResponseStatusException.class);
        verify(db, never()).update(startsWith("UPDATE prp_mcp_write_drafts SET status='APPROVED'"),
            any(), any());
    }

    @Test void approvedAppClickTransitionsOnlyAnOwnedFreshHealthCreateDraft() throws Exception {
        auth(CLIENT);
        stubPendingApprovalQuery("WELLNESS_CREATE", "PENDING", false, "meal");
        when(db.update(startsWith("UPDATE prp_mcp_write_drafts SET status='APPROVED',approved_at=CURRENT_TIMESTAMP"),
            eq(ID), eq(2L))).thenReturn(1);
        assertThat(drafts(true).approveFromChatgptUi(ID, "approve").status()).isEqualTo("APPROVED");
        verify(db).update(startsWith("UPDATE prp_mcp_write_drafts SET status='APPROVED',approved_at=CURRENT_TIMESTAMP"),
            eq(ID), eq(2L));
    }

    @Test void updateAndExpiredDraftsCannotUseChatApproval() throws Exception {
        auth(CLIENT);
        stubPendingApprovalQuery("WELLNESS_UPDATE", "PENDING", false, "meal");
        assertThatThrownBy(() -> drafts(true).approveFromChatgptUi(ID,"approve"))
            .isInstanceOf(ResponseStatusException.class);
        reset(db);
        stubPendingApprovalQuery("WELLNESS_CREATE", "PENDING", true, "meal");
        assertThatThrownBy(() -> drafts(true).approveFromChatgptUi(ID,"approve"))
            .isInstanceOf(ResponseStatusException.class);
        verify(db, never()).update(startsWith("UPDATE prp_mcp_write_drafts SET status='APPROVED'"),
            any(), any());
    }

    @Test void nonMealHealthCreateCannotUseChatApproval() throws Exception {
        auth(CLIENT);
        stubPendingApprovalQuery("WELLNESS_CREATE", "PENDING", false, "exercise");
        assertThatThrownBy(() -> drafts(true).approveFromChatgptUi(ID, "approve"))
            .isInstanceOf(ResponseStatusException.class);
        verify(db, never()).update(startsWith("UPDATE prp_mcp_write_drafts SET status='APPROVED'"),
            any(), any());
    }

    @Test void rejectingDraftDoesNotWriteBusinessData() throws Exception {
        auth(CLIENT);
        stubPendingApprovalQuery("WELLNESS_CREATE", "PENDING", false, "meal");
        when(db.update(startsWith("UPDATE prp_mcp_write_drafts SET status='REJECTED'"),
            eq(ID), eq(2L))).thenReturn(1);
        assertThat(drafts(true).approveFromChatgptUi(ID, "reject").status()).isEqualTo("REJECTED");
        verify(db).update(startsWith("UPDATE prp_mcp_write_drafts SET status='REJECTED'"),
            eq(ID), eq(2L));
        verify(db, never()).update(startsWith("UPDATE prp_mcp_write_drafts SET status='CONSUMED'"),
            any(), any(), any());
    }

    private void taskAuth(String client, Set<String> grants) {
        var user = new UserProfile(2L, "owner", "Owner");
        var auth = new UsernamePasswordAuthenticationToken(user, null, List.of(
            new SimpleGrantedAuthority("SCOPE_prp.write.create"),
            new SimpleGrantedAuthority("SCOPE_prp.write.confirm")));
        auth.setDetails(new McpScopeGuard.VerifiedClient(client, grants));
        SecurityContextHolder.getContext().setAuthentication(auth);
    }

    @Test void taskApprovalRequiresPendingTaskTestOriginAndBothOwnerGrants() throws Exception {
        var both = Set.of("prp.write.create", "prp.write.confirm");
        var candidate = drafts(false, McpTaskApprovalUiConfiguration.TEST_RESOURCE);
        taskAuth(CLIENT, both);
        stubPendingApprovalQuery("TASK", "PENDING", false, "");
        assertThatThrownBy(() -> candidate.approveTaskFromChatgptUi(ID, "approve"))
            .isInstanceOf(ResponseStatusException.class);
        ReflectionTestUtils.setField(candidate, "chatgptTaskApprovalUiEnabled", true);
        taskAuth(CLIENT, Set.of("prp.write.confirm"));
        assertThatThrownBy(() -> candidate.approveTaskFromChatgptUi(ID, "approve"))
            .isInstanceOf(ResponseStatusException.class);
        taskAuth("unreviewed-client", both);
        assertThatThrownBy(() -> candidate.approveTaskFromChatgptUi(ID, "approve"))
            .isInstanceOf(ResponseStatusException.class);
        taskAuth(CLIENT, both);
        var prod = drafts(false);
        ReflectionTestUtils.setField(prod, "chatgptTaskApprovalUiEnabled", true);
        assertThatThrownBy(() -> prod.approveTaskFromChatgptUi(ID, "approve"))
            .isInstanceOf(ResponseStatusException.class);
        when(db.update(startsWith("UPDATE prp_mcp_write_drafts SET status='APPROVED'"),
            eq(ID), eq(2L))).thenReturn(1);
        assertThat(candidate.approveTaskFromChatgptUi(ID, "approve").status()).isEqualTo("APPROVED");
        verify(db, times(1)).update(startsWith("UPDATE prp_mcp_write_drafts SET status='APPROVED'"),
            eq(ID), eq(2L));
    }

    @Test void taskCardRejectsOtherKindsAndNeverWritesARejectedTask() throws Exception {
        var candidate = drafts(false, McpTaskApprovalUiConfiguration.TEST_RESOURCE);
        ReflectionTestUtils.setField(candidate, "chatgptTaskApprovalUiEnabled", true);
        taskAuth(CLIENT, Set.of("prp.write.create", "prp.write.confirm"));
        for (String kind : List.of("TASK_UPDATE", "TASK_DELETE", "FINANCE", "WELLNESS_CREATE")) {
            stubPendingApprovalQuery(kind, "PENDING", false, "");
            assertThatThrownBy(() -> candidate.approveTaskFromChatgptUi(ID, "approve"))
                .isInstanceOf(ResponseStatusException.class);
        }
        stubPendingApprovalQuery("TASK", "PENDING", true, "");
        assertThatThrownBy(() -> candidate.approveTaskFromChatgptUi(ID, "approve"))
            .isInstanceOf(ResponseStatusException.class);
        stubPendingApprovalQuery("TASK", "PENDING", false, "");
        when(db.update(startsWith("UPDATE prp_mcp_write_drafts SET status='REJECTED'"),
            eq(ID), eq(2L))).thenReturn(1);
        assertThat(candidate.approveTaskFromChatgptUi(ID, "reject").status()).isEqualTo("REJECTED");
        verify(db, never()).update(startsWith("UPDATE prp_mcp_write_drafts SET status='APPROVED'"),
            any(), any());
        verify(db, never()).update(startsWith("UPDATE prp_mcp_write_drafts SET status='CONSUMED'"),
            any(), any(), any());
    }

    @Test void taskCardFlagDoesNotAllowRegularConfirmToSavePendingTask() throws Exception {
        var candidate = drafts(false, McpTaskApprovalUiConfiguration.TEST_RESOURCE);
        ReflectionTestUtils.setField(candidate, "chatgptTaskApprovalUiEnabled", true);
        taskAuth(CLIENT, Set.of("prp.write.create", "prp.write.confirm"));
        stubPendingConfirmQuery("TASK");
        assertThatThrownBy(() -> candidate.confirm(ID))
            .isInstanceOfSatisfying(ResponseStatusException.class,
                ex -> assertThat(ex.getStatusCode()).isEqualTo(HttpStatus.CONFLICT));
        verify(db, never()).update(startsWith("UPDATE prp_mcp_write_drafts SET status='CONSUMED'"),
            any(), any(), any());
    }
}
