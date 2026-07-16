package com.matrix.prp.dashboard.api;

import com.matrix.prp.common.api.ApiResponse;
import com.matrix.prp.dashboard.model.DashboardModule;
import com.matrix.prp.dashboard.model.DashboardSummary;
import com.matrix.prp.finance.model.FinanceMonthlySummary;
import com.matrix.prp.finance.service.FinanceService;
import com.matrix.prp.modules.service.ModuleService;
import com.matrix.prp.records.model.RecordFilter;
import com.matrix.prp.records.service.RecordService;
import com.matrix.prp.tasks.model.TaskFilter;
import com.matrix.prp.tasks.model.TaskItem;
import com.matrix.prp.tasks.service.TaskService;
import java.time.LocalDate;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/dashboard")
public class DashboardController {

    private final RecordService recordService;
    private final TaskService taskService;
    private final FinanceService financeService;
    private final ModuleService moduleService;

    public DashboardController(
            RecordService recordService,
            TaskService taskService,
            FinanceService financeService,
            ModuleService moduleService) {
        this.recordService = recordService;
        this.taskService = taskService;
        this.financeService = financeService;
        this.moduleService = moduleService;
    }

    @GetMapping("/summary")
    public ApiResponse<DashboardSummary> summary() {
        LocalDate today = LocalDate.now();
        FinanceMonthlySummary financeSummary = financeService.monthlySummary();
        List<TaskItem> activeTasks = taskService.list().stream()
                .filter(task -> !"done".equals(task.status()))
                .filter(task -> !"canceled".equals(task.status()))
                .toList();
        DashboardSummary summary = new DashboardSummary(
                today,
                taskService.todayCount(),
                (int) activeTasks.stream()
                        .filter(task -> task.dueDate() != null && task.dueDate().isBefore(today))
                        .count(),
                recordService.count(),
                financeSummary.income(),
                financeSummary.expense(),
                financeSummary.balance(),
                taskService.list(new TaskFilter(null, null, today, null)).stream()
                        .filter(task -> !"done".equals(task.status()))
                        .limit(5)
                        .toList(),
                activeTasks.stream()
                        .filter(task -> "high".equals(task.priority()))
                        .limit(5)
                        .toList(),
                recordService.list(new RecordFilter(null, null, null, null)).stream()
                        .limit(5)
                        .toList(),
                moduleService.listFeatures().stream()
                        .map(module -> new DashboardModule(
                                module.code(),
                                module.name(),
                                module.description(),
                                module.enabled()))
                        .toList());

        return ApiResponse.success(summary);
    }
}
