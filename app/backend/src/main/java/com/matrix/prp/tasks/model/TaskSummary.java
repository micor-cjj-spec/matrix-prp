package com.matrix.prp.tasks.model;

import java.util.Map;

public record TaskSummary(
        int openCount,
        int todayCount,
        int unscheduledCount,
        int overdueCount,
        int upcomingSevenDaysCount,
        int highPriorityOpenCount,
        Map<String, Integer> statusCounts) {
}
