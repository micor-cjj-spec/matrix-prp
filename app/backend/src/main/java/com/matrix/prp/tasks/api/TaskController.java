package com.matrix.prp.tasks.api;

import com.matrix.prp.common.api.ApiResponse;
import com.matrix.prp.tasks.model.CreateTaskRequest;
import com.matrix.prp.tasks.model.TaskFilter;
import com.matrix.prp.tasks.model.TaskItem;
import com.matrix.prp.tasks.model.TaskSummary;
import com.matrix.prp.tasks.service.TaskService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Pattern;
import java.time.LocalDate;
import java.util.List;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.validation.annotation.Validated;

@RestController
@Validated
@RequestMapping("/api/tasks")
public class TaskController {

    private final TaskService taskService;

    public TaskController(TaskService taskService) {
        this.taskService = taskService;
    }

    @GetMapping
    public ApiResponse<List<TaskItem>> list(
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String moduleCode,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate dueDate,
            @RequestParam(required = false) String priority) {
        return ApiResponse.success(taskService.list(new TaskFilter(status, moduleCode, dueDate, priority)));
    }

    @GetMapping("/summary")
    public ApiResponse<TaskSummary> summary() {
        return ApiResponse.success(taskService.summary());
    }

    @PostMapping
    public ApiResponse<TaskItem> create(@Valid @RequestBody CreateTaskRequest request) {
        return ApiResponse.success(taskService.create(request));
    }

    @PutMapping("/{id}")
    public ApiResponse<TaskItem> update(@PathVariable long id, @Valid @RequestBody CreateTaskRequest request) {
        return ApiResponse.success(taskService.update(id, request));
    }

    @PatchMapping("/{id}/status")
    public ApiResponse<TaskItem> updateStatus(
            @PathVariable long id,
            @RequestParam @Pattern(regexp = "todo|in_progress|done|canceled",
                    message = "must be one of: todo, in_progress, done, canceled") String status) {
        return ApiResponse.success(taskService.updateStatus(id, status));
    }

    @DeleteMapping("/{id}")
    public ApiResponse<Void> delete(@PathVariable long id) {
        taskService.delete(id);
        return ApiResponse.success();
    }
}
