package com.matrix.prp.tasks.repository;

import com.matrix.prp.common.api.ResourceNotFoundException;
import com.matrix.prp.auth.security.TestTenant;
import java.util.concurrent.ConcurrentHashMap;
import com.matrix.prp.tasks.model.CreateTaskRequest;
import com.matrix.prp.tasks.model.TaskFilter;
import com.matrix.prp.tasks.model.TaskItem;
import java.time.OffsetDateTime;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;

@Repository
@Profile("test")
public class InMemoryTaskRepository implements TaskRepository {

    private final AtomicLong idGenerator = new AtomicLong(2000);
    private final CopyOnWriteArrayList<TaskItem> tasks = new CopyOnWriteArrayList<>();
    private final Map<Long,Long> owners = new ConcurrentHashMap<>();

    @Override
    public List<TaskItem> list() {
        return list(new TaskFilter(null, null, null, null));
    }

    @Override
    public List<TaskItem> list(TaskFilter filter) {
        TaskFilter effectiveFilter = filter == null ? new TaskFilter(null, null, null, null) : filter;
        return tasks.stream()
                .filter(item -> java.util.Objects.equals(owners.get(item.id()), TestTenant.id()))
                .filter(task -> effectiveFilter.status() == null || effectiveFilter.status().isBlank()
                        || effectiveFilter.status().equals(task.status()))
                .filter(task -> effectiveFilter.moduleCode() == null || effectiveFilter.moduleCode().isBlank()
                        || effectiveFilter.moduleCode().equals(task.moduleCode()))
                .filter(task -> effectiveFilter.dueDate() == null
                        || effectiveFilter.dueDate().equals(task.dueDate()))
                .filter(task -> effectiveFilter.priority() == null || effectiveFilter.priority().isBlank()
                        || effectiveFilter.priority().equals(task.priority()))
                .sorted(Comparator.comparing(TaskItem::createdAt).reversed())
                .toList();
    }

    @Override
    public TaskItem create(CreateTaskRequest request) {
        TaskItem task = new TaskItem(
                idGenerator.incrementAndGet(),
                request.moduleCode(),
                request.title(),
                request.description() == null ? "" : request.description(),
                request.priority() == null ? "medium" : request.priority(),
                "todo",
                request.dueDate(),
                OffsetDateTime.now(),
                null);
        tasks.add(task);
        owners.put(task.id(), TestTenant.id());
        return task;
    }

    @Override
    public TaskItem update(long id, CreateTaskRequest request) {
        TaskItem existing = findById(id);
        TaskItem updated = new TaskItem(
                existing.id(),
                request.moduleCode(),
                request.title(),
                request.description() == null ? "" : request.description(),
                request.priority() == null ? "medium" : request.priority(),
                existing.status(),
                request.dueDate(),
                existing.createdAt(),
                existing.completedAt());
        tasks.remove(existing);
        tasks.add(updated);
        return updated;
    }

    @Override
    public TaskItem updateStatus(long id, String status) {
        TaskItem task = findById(id);
        TaskItem updated = new TaskItem(
                task.id(),
                task.moduleCode(),
                task.title(),
                task.description(),
                task.priority(),
                status,
                task.dueDate(),
                task.createdAt(),
                "done".equals(status) ? OffsetDateTime.now() : null);
        tasks.remove(task);
        tasks.add(updated);
        return updated;
    }

    @Override
    public void delete(long id) {
        boolean removed = tasks.removeIf(task -> task.id() == id && java.util.Objects.equals(owners.get(id), TestTenant.id()));
        if (!removed) {
            throw new ResourceNotFoundException("Task not found: " + id);
        }
    }


    private TaskItem findById(long id) {
        return tasks.stream()
                .filter(task -> task.id() == id && java.util.Objects.equals(owners.get(id), TestTenant.id()))
                .findFirst()
                .orElseThrow(() -> new ResourceNotFoundException("Task not found: " + id));
    }
}
