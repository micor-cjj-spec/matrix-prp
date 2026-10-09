package com.matrix.prp.tasks.model;

import java.time.LocalDate;
import java.util.List;

/** One consistent snapshot for task counters and workbench lists. */
public record TaskOverview(
        LocalDate date,
        TaskSummary summary,
        List<TaskItem> todayTasks,
        List<TaskItem> overdueTasks,
        List<TaskItem> unscheduledTasks,
        List<TaskItem> highPriorityTasks) {
}
