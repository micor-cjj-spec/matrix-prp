package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;

import com.matrix.prp.finance.model.CreateFinanceTransactionRequest;
import com.matrix.prp.finance.model.FinanceTransactionFilter;
import com.matrix.prp.finance.service.FinanceService;
import com.matrix.prp.modules.service.ModuleService;
import com.matrix.prp.records.model.CreateRecordRequest;
import com.matrix.prp.records.model.RecordFilter;
import com.matrix.prp.records.service.RecordService;
import com.matrix.prp.reviews.model.CreateReviewRequest;
import com.matrix.prp.reviews.model.ReviewFilter;
import com.matrix.prp.reviews.service.ReviewService;
import com.matrix.prp.tags.model.CreateTagRequest;
import com.matrix.prp.tags.model.UpdateTagRequest;
import com.matrix.prp.tags.service.TagService;
import com.matrix.prp.tasks.model.CreateTaskRequest;
import com.matrix.prp.tasks.model.TaskFilter;
import com.matrix.prp.tasks.service.TaskService;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.YearMonth;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@ActiveProfiles("test")
@SpringBootTest
class PhaseOneServiceTests {

    @Autowired
    private RecordService recordService;

    @Autowired
    private TaskService taskService;

    @Autowired
    private FinanceService financeService;

    @Autowired
    private ReviewService reviewService;

    @Autowired
    private ModuleService moduleService;

    @Autowired
    private TagService tagService;

    @Test
    void createsRecordTaskFinanceTransactionAndReview() {
        var tag = tagService.create(new CreateTagRequest(
                "phase-one",
                "#1d4ed8",
                "Phase one foundation"));
        var updatedTag = tagService.create(new CreateTagRequest(
                "review",
                "#047857",
                "Review records"));
        var record = recordService.create(new CreateRecordRequest(
                "work",
                "Finish phase one persistence",
                "Add repository layer and MySQL schema.",
                LocalDate.now(),
                List.of(tag.id())));
        var task = taskService.create(new CreateTaskRequest(
                "work",
                "Verify backend tests",
                null,
                null,
                LocalDate.now()));
        var transaction = financeService.createTransaction(new CreateFinanceTransactionRequest(
                "expense",
                new BigDecimal("19.90"),
                "tools",
                null,
                null,
                null,
                LocalDate.now()));
        var review = reviewService.create(new CreateReviewRequest(
                "weekly",
                "work",
                "Week 29 review",
                "Persistence foundation is taking shape.",
                "Repository split is now testable.",
                "Docker Desktop still needs to be started for MySQL runtime checks.",
                "Wire review UI next.",
                LocalDate.now().minusDays(6),
                LocalDate.now()));
        assertThat(record.id()).isPositive();
        assertThat(record.tags()).extracting("id").contains(tag.id());
        assertThat(recordService.count()).isEqualTo(1);
        assertThat(recordService.list(new RecordFilter("work", null, null, null))).hasSize(1);
        assertThat(recordService.list(new RecordFilter("life", null, null, null))).isEmpty();
        assertThat(recordService.list(new RecordFilter(null, tag.id(), null, null))).hasSize(1);
        assertThat(recordService.list(new RecordFilter(null, 999L, null, null))).isEmpty();
        assertThat(recordService.list(new RecordFilter(null, null, LocalDate.now(), null))).hasSize(1);
        assertThat(recordService.list(new RecordFilter(null, null, null, "MySQL"))).hasSize(1);
        assertThat(recordService.list(new RecordFilter(null, null, null, "not-found"))).isEmpty();
        var updatedRecord = recordService.update(record.id(), new CreateRecordRequest(
                "learning",
                "Review phase one persistence",
                "Record update and delete are now part of the loop.",
                LocalDate.now(),
                List.of(updatedTag.id())));
        assertThat(updatedRecord.moduleCode()).isEqualTo("learning");
        assertThat(updatedRecord.tags()).extracting("id").containsExactly(updatedTag.id());
        assertThat(recordService.list(new RecordFilter("work", null, null, null))).isEmpty();
        assertThat(recordService.list(new RecordFilter("learning", updatedTag.id(), LocalDate.now(), "update"))).hasSize(1);
        recordService.delete(record.id());
        assertThat(recordService.count()).isZero();
        assertThat(task.status()).isEqualTo("todo");
        assertThat(taskService.todayCount()).isEqualTo(1);
        var updatedTask = taskService.update(task.id(), new CreateTaskRequest(
                "learning",
                "Verify task editing",
                "Task update is part of the first phase loop.",
                "high",
                LocalDate.now()));
        assertThat(updatedTask.moduleCode()).isEqualTo("learning");
        assertThat(updatedTask.priority()).isEqualTo("high");
        assertThat(taskService.list(new TaskFilter("todo", "learning", LocalDate.now(), "high"))).hasSize(1);
        assertThat(taskService.list(new TaskFilter("todo", "learning", LocalDate.now(), "low"))).isEmpty();
        assertThat(taskService.list(new TaskFilter("done", null, null, null))).isEmpty();
        var completedTask = taskService.updateStatus(task.id(), "done");
        assertThat(completedTask.completedAt()).isNotNull();
        assertThat(taskService.list(new TaskFilter("done", "learning", LocalDate.now(), "high"))).hasSize(1);
        assertThat(taskService.todayCount()).isZero();
        taskService.delete(task.id());
        assertThat(taskService.list()).isEmpty();
        assertThat(transaction.account()).isEqualTo("default");
        assertThat(financeService.monthlySummary().expense()).isEqualByComparingTo("19.90");
        assertThat(financeService.listTransactions(new FinanceTransactionFilter(YearMonth.now(), "expense", "tools"))).hasSize(1);
        assertThat(financeService.monthlyCategorySummary(new FinanceTransactionFilter(YearMonth.now(), "expense", null)))
                .extracting("category")
                .containsExactly("tools");
        assertThat(financeService.monthlyCategorySummary(new FinanceTransactionFilter(YearMonth.now(), "expense", null)).get(0).ratio())
                .isEqualByComparingTo("1.0000");
        var updatedTransaction = financeService.updateTransaction(transaction.id(), new CreateFinanceTransactionRequest(
                "income",
                new BigDecimal("299.00"),
                "salary",
                "bank",
                "client",
                "Updated finance transaction.",
                LocalDate.now()));
        assertThat(updatedTransaction.type()).isEqualTo("income");
        assertThat(updatedTransaction.amount()).isEqualByComparingTo("299.00");
        assertThat(financeService.monthlySummary(new FinanceTransactionFilter(YearMonth.now(), null, null)).income())
                .isEqualByComparingTo("299.00");
        financeService.deleteTransaction(transaction.id());
        assertThat(financeService.listTransactions()).isEmpty();
        assertThat(review.reviewType()).isEqualTo("weekly");
        assertThat(reviewService.list()).hasSize(1);
        var updatedReview = reviewService.update(review.id(), new CreateReviewRequest(
                "monthly",
                "learning",
                "Month 7 review",
                "Review editing is now available.",
                "The review loop can be maintained after creation.",
                "Need richer review insights later.",
                "Connect reviews with dashboard.",
                LocalDate.now().minusDays(29),
                LocalDate.now()));
        assertThat(updatedReview.reviewType()).isEqualTo("monthly");
        assertThat(updatedReview.moduleCode()).isEqualTo("learning");
        assertThat(updatedReview.nextActions()).contains("dashboard");
        assertThat(reviewService.list(new ReviewFilter("monthly", "learning", LocalDate.now().minusDays(31), LocalDate.now())))
                .hasSize(1);
        assertThat(reviewService.list(new ReviewFilter("weekly", "learning", null, null))).isEmpty();
        assertThat(reviewService.list(new ReviewFilter(null, "work", null, null))).isEmpty();
        assertThat(reviewService.list(new ReviewFilter(null, null, LocalDate.now().plusDays(1), null))).isEmpty();
        reviewService.delete(review.id());
        assertThat(reviewService.list()).isEmpty();
        assertThat(tag.name()).isEqualTo("phase-one");
        assertThat(tagService.list()).hasSize(2);
        var maintainedTag = tagService.update(updatedTag.id(), new UpdateTagRequest(
                "review-loop",
                "#0f766e",
                "Review and planning loop"));
        assertThat(maintainedTag.name()).isEqualTo("review-loop");
        assertThat(maintainedTag.color()).isEqualTo("#0f766e");
        tagService.delete(tag.id());
        assertThat(tagService.list()).extracting("id").containsExactly(maintainedTag.id());
        assertThat(moduleService.listFeatures()).extracting("code").contains("records", "tasks", "finance", "reviews");
        assertThat(moduleService.listDomains()).extracting("code").contains("life", "learning", "work", "interests", "social");
    }
}
