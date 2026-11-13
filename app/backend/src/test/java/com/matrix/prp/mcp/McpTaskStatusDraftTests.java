package com.matrix.prp.mcp;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.finance.service.FinanceService;
import com.matrix.prp.records.service.RecordService;
import com.matrix.prp.tasks.model.TaskItem;
import com.matrix.prp.tasks.service.TaskService;
import jakarta.validation.Validator;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.server.ResponseStatusException;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/**
 * Status-only draft must not alter user data or ask an AI to re-send
 * the title, description, module, priority, and due date.
 */
class McpTaskStatusDraftTests {
    @AfterEach void cleanup() { SecurityContextHolder.clearContext(); }

    @Test
    @SuppressWarnings({"unchecked", "rawtypes"})
    void preparesOwnerBoundStatusOnlyDraftWithoutAnyTaskMutation() {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(
                new UserProfile(2L, "synthetic", "Test"), null, List.of()));
        JdbcTemplate db = mock(JdbcTemplate.class);
        TaskService tasks = mock(TaskService.class);
        Validator validator = mock(Validator.class);
        var previous = new TaskItem(42L, "work", "Keep the original title",
            "Don't lose this description", "high", "todo",
            LocalDate.of(2026, 11, 20), OffsetDateTime.parse("2026-11-11T10:00:00+08:00"), null);
        when(tasks.get(42L)).thenReturn(previous);
        when(db.query(startsWith("SELECT updated_at FROM prp_tasks"), any(RowMapper.class),
            eq(42L), eq(2L))).thenReturn(List.of("2026-11-13 10:00:00"));
        when(db.queryForObject(startsWith("SELECT COUNT(*) FROM prp_mcp_write_drafts"),
            eq(Integer.class), eq(2L))).thenReturn(0);

        var drafts = new McpDraftService(db, new ObjectMapper().findAndRegisterModules(),
            validator, tasks, mock(FinanceService.class), mock(RecordService.class),
            mock(UserStore.class), mock(PasswordEncoder.class), true, "");
        var preview = drafts.prepareTaskStatus(42L, "in_progress");

        assertThat(preview.kind()).isEqualTo("TASK_UPDATE");
        assertThat(preview.values().path("taskId").asLong()).isEqualTo(42L);
        assertThat(preview.values().path("before").path("title").asText())
            .isEqualTo("Keep the original title");
        assertThat(preview.values().path("status").asText()).isEqualTo("in_progress");
        assertThat(preview.values().path("after").isNull()).isTrue();
        verify(db).update(startsWith("INSERT INTO prp_mcp_write_drafts"),
            any(), eq(2L), eq("TASK_UPDATE"), any(), any());
        verify(tasks, never()).updateStatus(anyLong(), anyString());
        verify(tasks, never()).update(anyLong(), any());
        verify(tasks, never()).create(any());
    }

    @Test
    void invalidStatusIsRejectedBeforeAnyDatabaseLookup() {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(
                new UserProfile(2L, "synthetic", "Test"), null, List.of()));
        JdbcTemplate db = mock(JdbcTemplate.class);
        TaskService tasks = mock(TaskService.class);
        var drafts = new McpDraftService(db, new ObjectMapper().findAndRegisterModules(),
            mock(Validator.class), tasks, mock(FinanceService.class),
            mock(RecordService.class), mock(UserStore.class),
            mock(PasswordEncoder.class), true, "");
        for (String status : List.of("blocked", "DONE", "", "todo;DROP")) {
            assertThatThrownBy(() -> drafts.prepareTaskStatus(42L, status))
                .isInstanceOf(ResponseStatusException.class);
        }
        verifyNoInteractions(db, tasks);
    }
}
