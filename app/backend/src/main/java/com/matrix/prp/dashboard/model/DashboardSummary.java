package com.matrix.prp.dashboard.model;

import com.matrix.prp.records.model.RecordItem;
import com.matrix.prp.tasks.model.TaskItem;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

public record DashboardSummary(
        LocalDate date,
        int todayTaskCount,
        int overdueTaskCount,
        int unscheduledTaskCount,
        int recentRecordCount,
        BigDecimal monthlyIncome,
        BigDecimal monthlyExpense,
        BigDecimal monthlyBalance,
        List<TaskItem> todayTasks,
        List<TaskItem> overdueTasks,
        List<TaskItem> unscheduledTasks,
        List<TaskItem> highPriorityTasks,
        List<RecordItem> recentRecords,
        List<DashboardModule> modules) {
}
