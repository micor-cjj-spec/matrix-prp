package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import com.baomidou.mybatisplus.core.conditions.Wrapper;
import com.baomidou.mybatisplus.core.conditions.AbstractWrapper;
import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.tasks.entity.TaskEntity;
import com.matrix.prp.tasks.mapper.TaskMapper;
import com.matrix.prp.tasks.model.TaskFilter;
import com.matrix.prp.tasks.repository.MyBatisTaskRepository;
import com.matrix.prp.tasks.service.TaskService;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;

/**
 * REVIEW-ONLY producer data boundary: exercises the actual MyBatis
 * TaskService.listLimited call, with a mocked mapper instead of a live DB.
 * No HTTP service, external identity, grants, credentials, or real users.
 * A verified producer principal is still a separate UNIMPLEMENTED G0-C gate.
 */
class TaskReadProducerBoundaryTests {
    private void asOwner(long id) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(
                new UserProfile(id, "ci_owner_" + id, "Synthetic CI owner"), null, List.of()));
    }

    @AfterEach void clear() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void eachAuthenticatedOwnerHasOwnSqlUserFilterAndDatabaseLimit() {
        TaskMapper mapper = mock(TaskMapper.class);
        when(mapper.selectList(any())).thenReturn(List.of());
        var tasks = new TaskService(new MyBatisTaskRepository(mapper));
        asOwner(12001);
        assertThat(tasks.listLimited(new TaskFilter(null, null, null, null), 20)).isEmpty();
        asOwner(12002);
        assertThat(tasks.listLimited(new TaskFilter("todo", null, null, null), 20)).isEmpty();

        @SuppressWarnings({"raw", "unchecked"})
        ArgumentCaptor<Wrapper<TaskEntity>> captured = ArgumentCaptor.forClass((Class) Wrapper.class);
        verify(mapper, times(2)).selectList(captured.capture());
        List<Wrapper<TaskEntity>> sql = captured.getAllValues();
        assertThat(sql).hasSize(2);
        assertThat(sql.get(0).getSqlSegment().toLowerCase()).contains("user_id", "limit 20");
        assertThat(sql.get(1).getSqlSegment().toLowerCase()).contains("user_id", "status", "limit 20");
        assertThat(((AbstractWrapper<?, ?, ?>) sql.get(0)).getParamNameValuePairs().values()).contains(12001L).doesNotContain(12002L);
        assertThat(((AbstractWrapper<?, ?, ?>) sql.get(1)).getParamNameValuePairs().values()).contains(12002L, "todo").doesNotContain(12001L);
    }

    @Test
    void noTrustedProducerPrincipalFailsClosedBeforeMapperRead() {
        TaskMapper mapper = mock(TaskMapper.class);
        var tasks = new TaskService(new MyBatisTaskRepository(mapper));
        assertThatThrownBy(() -> tasks.listLimited(new TaskFilter(null, null, null, null), 20))
            .isInstanceOf(ResponseStatusException.class);
        verifyNoInteractions(mapper);
    }

    @Test
    void sqlLimitRejectsUnboundedAndInvalidRequest() {
        TaskMapper mapper = mock(TaskMapper.class);
        var tasks = new TaskService(new MyBatisTaskRepository(mapper));
        asOwner(12001);
        for (int limit : new int[]{0, -1, 101, Integer.MAX_VALUE}) {
            assertThatThrownBy(() -> tasks.listLimited(new TaskFilter(null, null, null, null), limit))
                .isInstanceOf(IllegalArgumentException.class);
        }
        verifyNoInteractions(mapper);
    }
}
