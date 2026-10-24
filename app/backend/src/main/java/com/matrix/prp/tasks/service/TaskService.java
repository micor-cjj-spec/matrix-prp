package com.matrix.prp.tasks.service;

import com.matrix.prp.tasks.model.CreateTaskRequest;
import com.matrix.prp.tasks.model.TaskFilter;
import com.matrix.prp.tasks.model.TaskItem;
import com.matrix.prp.tasks.model.TaskOverview;
import com.matrix.prp.tasks.model.TaskSummary;
import com.matrix.prp.tasks.repository.TaskRepository;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;

@Service
public class TaskService {

    private final TaskRepository taskRepository;

    public TaskService(TaskRepository taskRepository) {
        this.taskRepository = taskRepository;
    }

    public List<TaskItem> list() {
        return taskRepository.list();
    }

    public TaskItem get(long id) {
        if (id <= 0) throw new org.springframework.web.server.ResponseStatusException(
            org.springframework.http.HttpStatus.BAD_REQUEST, "Invalid task ID");
        return taskRepository.get(id);
    }

    public List<TaskItem> list(TaskFilter filter) {
        return taskRepository.list(filter);
    }

    /**
     * Use the same date, open-state predicate and task snapshot for all
     * dashboard lists and counters.
     *
     * Today means due today; tasks without a due date are "unscheduled".
     * Upcoming seven days means tomorrow through the seventh day.
     */
    public List<TaskItem> listLimited(TaskFilter filter, int limit) {
        return taskRepository.listLimited(filter, limit);
    }

    public TaskOverview overview() {
        LocalDate today = LocalDate.now();
        List<TaskItem> allTasks = taskRepository.list();
        List<TaskItem> openTasks = allTasks.stream().filter(this::isOpen).toList();
        List<TaskItem> todayTasks = openTasks.stream()
                .filter(task -> today.equals(task.dueDate()))
                .toList();
        List<TaskItem> overdueTasks = openTasks.stream()
                .filter(task -> task.dueDate() != null && task.dueDate().isBefore(today))
                .toList();
        List<TaskItem> unscheduledTasks = openTasks.stream()
                .filter(task -> task.dueDate() == null)
                .toList();
        List<TaskItem> highPriorityTasks = openTasks.stream()
                .filter(task -> "high".equals(task.priority()))
                .toList();

        Map<String, Integer> statusCounts = allTasks.stream()
                .collect(Collectors.groupingBy(TaskItem::status, Collectors.summingInt(task -> 1)));
        TaskSummary summary = new TaskSummary(
                openTasks.size(),
                todayTasks.size(),
                unscheduledTasks.size(),
                overdueTasks.size(),
                (int) openTasks.stream()
                        .filter(task -> task.dueDate() != null
                                && task.dueDate().isAfter(today)
                                && !task.dueDate().isAfter(today.plusDays(7)))
                        .count(),
                highPriorityTasks.size(),
                statusCounts);

        return new TaskOverview(today, summary,
                todayTasks, overdueTasks, unscheduledTasks, highPriorityTasks);
    }

    public TaskSummary summary() {
        return overview().summary();
    }

    public TaskItem create(CreateTaskRequest request) {
        return taskRepository.create(request);
    }

    public TaskItem update(long id, CreateTaskRequest request) {
        return taskRepository.update(id, request);
    }

    public TaskItem updateStatus(long id, String status) {
        return taskRepository.updateStatus(id, status);
    }

    public void delete(long id) {
        taskRepository.delete(id);
    }

    public int todayCount() {
        return overview().summary().todayCount();
    }

    private boolean isOpen(TaskItem task) {
        return !"done".equals(task.status()) && !"canceled".equals(task.status());
    }
}
