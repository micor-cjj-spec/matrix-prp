package com.matrix.prp.mcp;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.finance.model.CreateFinanceTransactionRequest;
import com.matrix.prp.finance.service.FinanceService;
import com.matrix.prp.records.service.RecordService;
import com.matrix.prp.tasks.model.CreateTaskRequest;
import com.matrix.prp.tasks.service.TaskService;
import jakarta.validation.Validation;
import java.math.BigDecimal;
import java.util.List;
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
            Validation.buildDefaultValidatorFactory().getValidator(), tasks, finance, records, enabled);
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
    void confirmationRequiresExplicitApprovalAndIsNotAnImplicitWrite() {
        assertThatThrownBy(() -> drafts(true).confirm("41abc027-d67e-4bdf-8985-e3ec97d23204", false))
            .isInstanceOf(ResponseStatusException.class);
        verifyNoInteractions(db, tasks, finance, records);
    }
}
