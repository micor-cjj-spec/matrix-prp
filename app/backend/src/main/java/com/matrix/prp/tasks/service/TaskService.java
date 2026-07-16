package com.matrix.prp.tasks.service;

import com.matrix.prp.tasks.model.CreateTaskRequest;
import com.matrix.prp.tasks.model.TaskFilter;
import com.matrix.prp.tasks.model.TaskItem;
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

    public List<TaskItem> list(TaskFilter filter) {
        return taskRepository.list(filter);
    }

    public TaskSummary summary() {
        LocalDate today = LocalDate.now();
        LocalDate sevenDaysLater = today.plusDays(7);
        List<TaskItem> tasks = taskRepository.list();
        Map<String, Integer> statusCounts = tasks.stream()
                .collect(Collectors.groupingBy(TaskItem::status, Collectors.summingInt(task -> 1)));
        List<TaskItem> openTasks = tasks.stream()
                .filter(this::isOpen)
                .toList();

        return new TaskSummary(
                openTasks.size(),
                (int) openTasks.stream().filter(task -> task.dueDate() == null || today.equals(task.dueDate())).count(),
                (int) openTasks.stream().filter(task -> task.dueDate() != null && task.dueDate().isBefore(today)).count(),
                (int) openTasks.stream()
                        .filter(task -> task.dueDate() != null
                                && !task.dueDate().isBefore(today)
                                && !task.dueDate().isAfter(sevenDaysLater))
                        .count(),
                (int) openTasks.stream().filter(task -> "high".equals(task.priority())).count(),
                statusCounts);
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
        return taskRepository.todayCount();
    }

    private boolean isOpen(TaskItem task) {
        return !"done".equals(task.status()) && !"canceled".equals(task.status());
    }
}
