package com.matrix.prp.mcp;

import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.common.api.ResourceNotFoundException;
import com.matrix.prp.tasks.model.CreateTaskRequest;
import com.matrix.prp.tasks.repository.InMemoryTaskRepository;
import com.matrix.prp.tasks.service.TaskService;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;
import static org.assertj.core.api.Assertions.*;

class McpTaskReadTests {
    private void user(long id) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(new UserProfile(id, "synthetic", "Test"), null, List.of()));
    }

    @AfterEach void cleanup() { SecurityContextHolder.clearContext(); }

    @Test void exactIdReadRemainsOwnerScopedAndDeletedTasksDisappear() {
        var service = new TaskService(new InMemoryTaskRepository());
        user(501);
        var task = service.create(new CreateTaskRequest("work", "Synthetic task", "", "low", null));
        assertThat(service.get(task.id())).isEqualTo(task);
        user(502);
        assertThatThrownBy(() -> service.get(task.id())).isInstanceOf(ResourceNotFoundException.class);
        assertThatThrownBy(() -> service.get(task.id() + 1)).isInstanceOf(ResourceNotFoundException.class);
        user(501);
        service.delete(task.id());
        assertThatThrownBy(() -> service.get(task.id())).isInstanceOf(ResourceNotFoundException.class);
    }

    @Test void nonpositiveIdsAreRejected() {
        var service = new TaskService(new InMemoryTaskRepository());
        assertThatThrownBy(() -> service.get(0)).isInstanceOf(ResponseStatusException.class);
        assertThatThrownBy(() -> service.get(-1)).isInstanceOf(ResponseStatusException.class);
    }
}
