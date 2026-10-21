package com.matrix.prp.mcp;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.finance.model.CreateFinanceTransactionRequest;
import com.matrix.prp.finance.service.FinanceService;
import com.matrix.prp.records.service.RecordService;
import com.matrix.prp.tasks.model.CreateTaskRequest;
import com.matrix.prp.tasks.service.TaskService;
import jakarta.validation.Validation;
import java.math.BigDecimal;
import java.util.List;
import java.time.LocalDateTime;
import java.sql.Timestamp;
import java.sql.ResultSet;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.startsWith;
import static org.mockito.Mockito.*;

class McpGatewayTests {
    private final JdbcTemplate db = mock(JdbcTemplate.class);
    private final TaskService tasks = mock(TaskService.class);
    private final FinanceService finance = mock(FinanceService.class);
    private final RecordService records = mock(RecordService.class);
    private final UserStore users = mock(UserStore.class);
    private final PasswordEncoder passwords = mock(PasswordEncoder.class);
    private final ObjectMapper json = new ObjectMapper().findAndRegisterModules();

    @BeforeEach
    void authenticated() {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(new UserProfile(501L, "mcp-user", "MCP"), null, List.of()));
    }

    @AfterEach
    void clearSecurity() {
        SecurityContextHolder.clearContext();
    }

    private McpDraftService drafts(boolean enabled) {
        return new McpDraftService(db, json,
            Validation.buildDefaultValidatorFactory().getValidator(), tasks, finance, records, users, passwords, enabled);
    }

    @Test
    void defaultWriteGateBlocksAllBusinessWrites() {
        var service = drafts(false);
        assertThatThrownBy(() -> service.prepare(McpDraftService.Kind.TASK,
            new CreateTaskRequest("work", "Safe title", "", "low", null)))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(ex -> assertThat(((ResponseStatusException) ex).getStatusCode())
                .isEqualTo(HttpStatus.FORBIDDEN));
        verifyNoInteractions(db, tasks, finance, records);
    }

    @Test
    void missingPrincipalFailsClosedBeforeDatabaseAccess() {
        SecurityContextHolder.clearContext();
        assertThatThrownBy(() -> drafts(true).prepare(McpDraftService.Kind.TASK,
            new CreateTaskRequest("work", "Safe title", "", "low", null)))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(ex -> assertThat(((ResponseStatusException) ex).getStatusCode())
                .isEqualTo(HttpStatus.UNAUTHORIZED));
        verifyNoInteractions(db, tasks, finance, records);
    }

    @Test
    void financeCannotPrepareNegativeAmount() {
        assertThatThrownBy(() -> drafts(true).prepare(McpDraftService.Kind.FINANCE,
            new CreateFinanceTransactionRequest("expense", new BigDecimal("-12.00"),
                "transport", "cash", null, null, null)))
            .isInstanceOf(ResponseStatusException.class);
        verifyNoInteractions(db, finance);
    }

    @Test
    void preparePersistsOwnerNotClientSelectedUserId() {
        when(db.queryForObject(any(String.class), eq(Integer.class), eq(501L))).thenReturn(0);
        var preview = drafts(true).prepare(McpDraftService.Kind.TASK,
            new CreateTaskRequest("work", "Review API contract", "", "high", null));
        assertThat(preview.kind()).isEqualTo("TASK");
        assertThat(preview.values().get("title").asText()).isEqualTo("Review API contract");
        verify(db).update(startsWith("INSERT INTO prp_mcp_write_drafts"),
            any(), eq(501L), eq("TASK"), any(), any());
        verifyNoInteractions(tasks, finance, records);
    }

    @Test
    void approvalRequiresSeparateHumanPasswordAndDoesNotWriteBusinessData() {
        assertThatThrownBy(() -> drafts(true).approve(
            "41abc027-d67e-4bdf-8985-e3ec97d23204", ""))
            .isInstanceOf(ResponseStatusException.class);
        verifyNoInteractions(db, tasks, finance, records);
    }

    @Test
    @SuppressWarnings("unchecked")
    void invalidPasswordConsumesAnAttemptWithoutCreatingBusinessData() throws Exception {
        String id = "41abc027-d67e-4bdf-8985-e3ec97d23204";
        when(db.query(startsWith("SELECT status,approval_failures"), any(RowMapper.class), eq(id), eq(501L)))
            .thenAnswer(invocation -> {
                RowMapper<Object> mapper = invocation.getArgument(1);
                ResultSet rs = mock(ResultSet.class);
                when(rs.getString("status")).thenReturn("PENDING");
                when(rs.getInt("approval_failures")).thenReturn(0);
                when(rs.getTimestamp("expires_at")).thenReturn(Timestamp.valueOf(LocalDateTime.now().plusMinutes(5)));
                return List.of(mapper.mapRow(rs, 0));
            });
        when(users.findById(501L)).thenReturn(java.util.Optional.of(
            new UserAccount(501L, "mcp-user", "MCP", "hashed-password", false, true)));
        when(passwords.matches(eq("wrong"), eq("hashed-password"))).thenReturn(false);

        var outcome = drafts(true).approve(id, "wrong");
        assertThat(outcome.status()).isEqualTo("INVALID_PASSWORD");
        assertThat(outcome.remainingAttempts()).isEqualTo(4);
        verify(db).update(startsWith("UPDATE prp_mcp_write_drafts SET approval_failures="),
            eq(1), eq("PENDING"), eq(id), eq(501L));
        verifyNoInteractions(tasks, finance, records);
    }

    @Test
    @SuppressWarnings("unchecked")
    void validPasswordApprovesButDoesNotSaveBusinessRecord() throws Exception {
        String id = "41abc027-d67e-4bdf-8985-e3ec97d23204";
        when(db.query(startsWith("SELECT status,approval_failures"), any(RowMapper.class), eq(id), eq(501L)))
            .thenAnswer(invocation -> {
                RowMapper<Object> mapper = invocation.getArgument(1);
                ResultSet rs = mock(ResultSet.class);
                when(rs.getString("status")).thenReturn("PENDING");
                when(rs.getInt("approval_failures")).thenReturn(0);
                when(rs.getTimestamp("expires_at")).thenReturn(Timestamp.valueOf(LocalDateTime.now().plusMinutes(5)));
                return List.of(mapper.mapRow(rs, 0));
            });
        when(users.findById(501L)).thenReturn(java.util.Optional.of(
            new UserAccount(501L, "mcp-user", "MCP", "hashed-password", false, true)));
        when(passwords.matches("correct", "hashed-password")).thenReturn(true);

        var outcome = drafts(true).approve(id, "correct");
        assertThat(outcome.status()).isEqualTo("APPROVED");
        verify(db).update(startsWith("UPDATE prp_mcp_write_drafts SET status='APPROVED'"),
            eq(id), eq(501L));
        verifyNoInteractions(tasks, finance, records);
    }

    @Test
    @SuppressWarnings("unchecked")
    void pendingDraftCannotConfirmWithoutServerSideApproval() throws Exception {
        String id = "41abc027-d67e-4bdf-8985-e3ec97d23204";
        when(db.query(startsWith("SELECT kind,payload_json,result_json,status,expires_at"),
            any(RowMapper.class), eq(id), eq(501L))).thenAnswer(invocation -> {
                RowMapper<Object> mapper = invocation.getArgument(1);
                ResultSet rs = mock(ResultSet.class);
                when(rs.getString("kind")).thenReturn("TASK");
                when(rs.getString("payload_json")).thenReturn("{}");
                when(rs.getString("result_json")).thenReturn(null);
                when(rs.getString("status")).thenReturn("PENDING");
                when(rs.getTimestamp("expires_at")).thenReturn(Timestamp.valueOf(LocalDateTime.now().plusMinutes(5)));
                return List.of(mapper.mapRow(rs, 0));
            });

        assertThatThrownBy(() -> drafts(true).confirm(id))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(ex -> assertThat(((ResponseStatusException) ex).getStatusCode())
                .isEqualTo(HttpStatus.CONFLICT));
        verifyNoInteractions(tasks, finance, records);
    }

    @Test
    void confirmOfUnknownDraftNeverWritesBusinessData() {
        assertThatThrownBy(() -> drafts(true).confirm("41abc027-d67e-4bdf-8985-e3ec97d23204"))
            .isInstanceOf(ResponseStatusException.class);
        verifyNoInteractions(tasks, finance, records);
    }
}
