package com.matrix.prp.dashboard.api;

import com.matrix.prp.common.api.ApiResponse;
import com.matrix.prp.dashboard.model.DashboardModule;
import com.matrix.prp.dashboard.model.DashboardSummary;
import com.matrix.prp.finance.model.FinanceMonthlySummary;
import com.matrix.prp.finance.service.FinanceService;
import com.matrix.prp.modules.service.ModuleService;
import com.matrix.prp.records.model.RecordFilter;
import com.matrix.prp.records.service.RecordService;
import com.matrix.prp.tasks.model.TaskOverview;
import com.matrix.prp.tasks.service.TaskService;
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
        TaskOverview tasks = taskService.overview();
        FinanceMonthlySummary financeSummary = financeService.monthlySummary();
        DashboardSummary summary = new DashboardSummary(
                tasks.date(),
                tasks.summary().todayCount(),
                tasks.summary().overdueCount(),
                tasks.summary().unscheduledCount(),
                recordService.count(),
                financeSummary.income(),
                financeSummary.expense(),
                financeSummary.balance(),
                tasks.todayTasks(),
                tasks.overdueTasks(),
                tasks.unscheduledTasks(),
                tasks.highPriorityTasks().stream().limit(5).toList(),
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
