package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;

import com.matrix.prp.tasks.model.CreateTaskRequest;
import com.matrix.prp.tasks.model.TaskOverview;
import com.matrix.prp.tasks.repository.InMemoryTaskRepository;
import com.matrix.prp.tasks.service.TaskService;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;

class TaskOverviewTests {

    @Test
    void separatesTodayOverdueUnscheduledFutureCompletedAndCanceled() {
        InMemoryTaskRepository repository = new InMemoryTaskRepository();
        TaskService service = new TaskService(repository);
        LocalDate today = LocalDate.now();

        var dueToday = service.create(request("today", "high", today));
        var overdue = service.create(request("overdue", "medium", today.minusDays(1)));
        var unscheduled = service.create(request("unscheduled", "high", null));
        var dueTomorrow = service.create(request("tomorrow", "medium", today.plusDays(1)));
        var dueAfterWindow = service.create(request("later", "low", today.plusDays(8)));
        var done = service.create(request("done", "high", today));
        var canceled = service.create(request("canceled", "high", null));
        service.updateStatus(done.id(), "done");
        service.updateStatus(canceled.id(), "canceled");

        TaskOverview overview = service.overview();

        assertThat(overview.date()).isEqualTo(today);
        assertThat(overview.todayTasks()).extracting("id").containsExactly(dueToday.id());
        assertThat(overview.overdueTasks()).extracting("id").containsExactly(overdue.id());
        assertThat(overview.unscheduledTasks()).extracting("id").containsExactly(unscheduled.id());
        assertThat(overview.highPriorityTasks()).extracting("id")
                .containsExactlyInAnyOrder(dueToday.id(), unscheduled.id());

        assertThat(overview.summary().openCount()).isEqualTo(5);
        assertThat(overview.summary().todayCount()).isEqualTo(overview.todayTasks().size());
        assertThat(overview.summary().overdueCount()).isEqualTo(overview.overdueTasks().size());
        assertThat(overview.summary().unscheduledCount()).isEqualTo(overview.unscheduledTasks().size());
        assertThat(overview.summary().upcomingSevenDaysCount()).isEqualTo(1);
        assertThat(overview.summary().highPriorityOpenCount()).isEqualTo(2);
        assertThat(overview.summary().statusCounts()).containsEntry("done", 1)
                .containsEntry("canceled", 1);
        assertThat(service.todayCount()).isEqualTo(1);

        assertThat(service.list()).extracting("id")
                .contains(dueTomorrow.id(), dueAfterWindow.id());
    }

    @Test
    void completingTaskImmediatelyUpdatesCountersAndLists() {
        InMemoryTaskRepository repository = new InMemoryTaskRepository();
        TaskService service = new TaskService(repository);
        var task = service.create(request("finish me", "medium", LocalDate.now()));

        assertThat(service.todayCount()).isEqualTo(1);
        service.updateStatus(task.id(), "done");

        assertThat(service.todayCount()).isZero();
        assertThat(service.overview().todayTasks()).isEmpty();
        assertThat(service.overview().summary().openCount()).isZero();
    }

    private CreateTaskRequest request(String title, String priority, LocalDate date) {
        return new CreateTaskRequest("learning", title, "", priority, date);
    }
}
