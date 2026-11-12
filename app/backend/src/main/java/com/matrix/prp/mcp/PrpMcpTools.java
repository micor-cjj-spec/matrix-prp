package com.matrix.prp.mcp;

import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.finance.model.CreateFinanceTransactionRequest;
import com.matrix.prp.finance.model.FinanceTransactionFilter;
import com.matrix.prp.finance.service.FinanceService;
import com.matrix.prp.records.model.CreateRecordRequest;
import com.matrix.prp.tasks.model.CreateTaskRequest;
import com.matrix.prp.tasks.model.TaskFilter;
import com.matrix.prp.tasks.service.TaskService;
import com.matrix.prp.wellness.WellnessService;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.YearMonth;
import java.util.List;
import java.util.Map;
import org.springaicommunity.mcp.annotation.McpTool;
import org.springaicommunity.mcp.annotation.McpToolParam;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

/**
 * Strictly scoped MCP tools; the MCP client may never choose the principal.
 * A transport without a valid PRP JWT fails closed via CurrentUser.
 */
@Component
@ConditionalOnProperty(prefix = "matrix-prp.mcp", name = "enabled", havingValue = "true")
public class PrpMcpTools {
    private final TaskService tasks;
    private final FinanceService finance;
    private final WellnessService wellness;
    private final McpDraftService drafts;
    private final McpScopeGuard scopes;

    public PrpMcpTools(TaskService tasks, FinanceService finance, WellnessService wellness,
                       McpDraftService drafts, McpScopeGuard scopes) {
        this.tasks = tasks;
        this.finance = finance;
        this.wellness = wellness;
        this.drafts = drafts;
        this.scopes = scopes;
    }

    @McpTool(name = "prp_tasks_list", description = "Read up to 20 tasks of the authenticated PRP user. Never reads other accounts.", annotations = @McpTool.McpAnnotations(readOnlyHint = true, destructiveHint = false, idempotentHint = true, openWorldHint = false))
    public Object listTasks(
            @McpToolParam(description = "Optional task status (todo, in_progress, done, canceled)", required = false)
            String status) {
        scopes.require("prp.tasks.read");
        if (status != null && !List.of("todo", "in_progress", "done", "canceled").contains(status)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid status");
        }
        return tasks.listLimited(new TaskFilter(status, null, null, null), 20);
    }

    @McpTool(name = "prp_task_get", description = "Read one task by its exact ID belonging to the authenticated PRP user. Missing and other-user tasks are both unavailable.", annotations = @McpTool.McpAnnotations(readOnlyHint = true, destructiveHint = false, idempotentHint = true, openWorldHint = false))
    public Object getTask(
            @McpToolParam(description = "Exact positive task ID returned by PRP", required = true) long taskId) {
        scopes.require("prp.tasks.read");
        return tasks.get(taskId);
    }

    @McpTool(name = "prp_finance_month", description = "Read monthly summary and up to 10 transactions belonging to the authenticated PRP user.", annotations = @McpTool.McpAnnotations(readOnlyHint = true, destructiveHint = false, idempotentHint = true, openWorldHint = false))
    public Object financeMonth(
            @McpToolParam(description = "Month in yyyy-MM; optional, defaults to the current month", required = false)
            String month) {
        scopes.require("prp.finance.read");
        YearMonth selected = month == null || month.isBlank() ? YearMonth.now() : yearMonth(month);
        FinanceTransactionFilter filter = new FinanceTransactionFilter(selected, null, null);
        return Map.of("month", selected.toString(), "summary", finance.monthlySummary(filter),
            "transactions", finance.listTransactionsLimited(filter, 10));
    }

    @McpTool(name = "prp_wellness_daily", description = "Read the authenticated PRP user's wellness daily record; never read another user's data.", annotations = @McpTool.McpAnnotations(readOnlyHint = true, destructiveHint = false, idempotentHint = true, openWorldHint = false))
    public Object wellnessDaily(
            @McpToolParam(description = "Date yyyy-MM-dd; optional, defaults to today", required = false)
            String date) {
        scopes.require("prp.wellness.read");
        return wellness.daily(date == null || date.isBlank() ? LocalDate.now() : localDate(date));
    }

    @McpTool(name = "prp_prepare_task", description = "Prepare a task creation draft only; does not create a task. Show exact fields to the user before confirmation.", annotations = @McpTool.McpAnnotations(readOnlyHint = false, destructiveHint = false, idempotentHint = false, openWorldHint = false))
    public McpDraftService.Preview prepareTask(
            @McpToolParam(description = "PRP module code, e.g. work, life, learning", required = true) String moduleCode,
            @McpToolParam(description = "Task title", required = true) String title,
            @McpToolParam(description = "Description", required = false) String description,
            @McpToolParam(description = "Priority: low, medium, high", required = false) String priority,
            @McpToolParam(description = "Due date in yyyy-MM-dd", required = false) String dueDate) {
        scopes.require("prp.write.create");
        return drafts.prepare(McpDraftService.Kind.TASK,
            new CreateTaskRequest(moduleCode, title, description, priority, optionalDate(dueDate)));
    }

    @McpTool(name = "prp_prepare_task_update", description = "Prepare an update to one owned task. Shows before and after values. Requires separate owner approval in PRP; never updates immediately.", annotations = @McpTool.McpAnnotations(readOnlyHint = false, destructiveHint = true, idempotentHint = false, openWorldHint = false))
    public McpDraftService.Preview prepareTaskUpdate(
            @McpToolParam(description = "Exact owned task ID", required = true) long taskId,
            @McpToolParam(description = "Replacement module code", required = true) String moduleCode,
            @McpToolParam(description = "Replacement title", required = true) String title,
            @McpToolParam(description = "Replacement description; omitted clears it", required = false) String description,
            @McpToolParam(description = "Replacement priority: low, medium, high", required = false) String priority,
            @McpToolParam(description = "Replacement due date yyyy-MM-dd", required = false) String dueDate,
            @McpToolParam(description = "Optional new status: todo, in_progress, done, canceled", required = false) String status) {
        scopes.require("prp.write.update");
        return drafts.prepareTaskChange(taskId,
            new CreateTaskRequest(moduleCode, title, description, priority, optionalDate(dueDate)), status, false);
    }

    @McpTool(name = "prp_prepare_task_delete", description = "Prepare deletion of one owned task. Does not delete until the owner separately approves in PRP and confirms the draft. Changed records are rejected.", annotations = @McpTool.McpAnnotations(readOnlyHint = false, destructiveHint = true, idempotentHint = false, openWorldHint = false))
    public McpDraftService.Preview prepareTaskDelete(
            @McpToolParam(description = "Exact owned task ID", required = true) long taskId) {
        scopes.require("prp.write.delete");
        return drafts.prepareTaskChange(taskId, null, null, true);
    }

    @McpTool(name = "prp_prepare_finance", description = "Prepare a new income or expense draft only. Amount is decimal CNY; does not book any transaction until confirmed.", annotations = @McpTool.McpAnnotations(readOnlyHint = false, destructiveHint = false, idempotentHint = false, openWorldHint = false))
    public McpDraftService.Preview prepareFinance(
            @McpToolParam(description = "income or expense", required = true) String type,
            @McpToolParam(description = "Positive decimal amount, e.g. 23.50", required = true) String amount,
            @McpToolParam(description = "PRP finance category", required = true) String category,
            @McpToolParam(description = "PRP account", required = false) String account,
            @McpToolParam(description = "Merchant", required = false) String merchant,
            @McpToolParam(description = "Note", required = false) String note,
            @McpToolParam(description = "Transaction date yyyy-MM-dd", required = false) String date) {
        scopes.require("prp.write.create");
        BigDecimal value;
        try {
            value = new BigDecimal(amount);
        } catch (RuntimeException ex) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid monetary amount");
        }
        return drafts.prepare(McpDraftService.Kind.FINANCE,
            new CreateFinanceTransactionRequest(type, value, category, account, merchant, note, optionalDate(date)));
    }

    @McpTool(name = "prp_prepare_record", description = "Prepare a personal PRP work, life, or learning record; no business record is written until confirmed.", annotations = @McpTool.McpAnnotations(readOnlyHint = false, destructiveHint = false, idempotentHint = false, openWorldHint = false))
    public McpDraftService.Preview prepareRecord(
            @McpToolParam(description = "PRP module code", required = true) String moduleCode,
            @McpToolParam(description = "Record title", required = true) String title,
            @McpToolParam(description = "Record contents", required = false) String content,
            @McpToolParam(description = "Record date yyyy-MM-dd", required = false) String date) {
        scopes.require("prp.write.create");
        return drafts.prepare(McpDraftService.Kind.RECORD,
            new CreateRecordRequest(moduleCode, title, content, optionalDate(date), List.of()));
    }

    @McpTool(name = "prp_draft_status",
             description = "Check the authenticated user's MCP draft status. Approval is possible only by opening PRP and reentering the account password.", annotations = @McpTool.McpAnnotations(readOnlyHint = true, destructiveHint = false, idempotentHint = true, openWorldHint = false))
    public McpDraftService.Review draftStatus(
            @McpToolParam(description = "Exact draftId returned by prp_prepare_*", required = true) String draftId) {
        scopes.require("prp.write.status");
        return drafts.review(draftId);
    }

    @McpTool(name = "prp_confirm_draft",
             description = "Commit exactly one already APPROVED draft. The user must first open the PRP approval page and reenter their account password. Cannot approve a draft from an MCP tool call. Replays return the saved record.", annotations = @McpTool.McpAnnotations(readOnlyHint = false, destructiveHint = true, idempotentHint = true, openWorldHint = false))
    public McpDraftService.Result confirmDraft(
            @McpToolParam(description = "Exact draftId returned by prp_prepare_*", required = true) String draftId) {
        scopes.require("prp.write.confirm");
        // Recheck the operation permission at execution time, including after revocation.
        var review = drafts.review(draftId);
        scopes.require(McpDraftService.operationScope(review.kind()));
        return drafts.confirm(draftId);
    }

    @McpTool(name="prp_wellness_list", description="Read at most 50 of your own meal, exercise or metric records. Meals/exercise use one exact date; metric uses 1-90 days. Never reads another user.", annotations=@McpTool.McpAnnotations(readOnlyHint=true,destructiveHint=false,idempotentHint=true,openWorldHint=false))
    public Object wellnessList(
            @McpToolParam(description="meal, exercise or metric",required=true) String entity,
            @McpToolParam(description="yyyy-MM-dd, defaults to today for meal/exercise",required=false) String date,
            @McpToolParam(description="Metric history days 1-90, defaults 30",required=false) Integer days) {
        scopes.require("prp.wellness.read");
        McpWellnessSupport.table(entity);
        if(days!=null && (days<1 || days>90)) throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Days must be 1-90");
        LocalDate d=date==null || date.isBlank()?LocalDate.now():localDate(date);
        return switch(entity) {
            case "meal" -> wellness.meals(d).stream().limit(50).toList();
            case "exercise" -> wellness.exercises(d).stream().limit(50).toList();
            default -> wellness.metrics(days==null?30:days).stream().limit(50).toList();
        };
    }

    @McpTool(name="prp_wellness_get", description="Read one exact owned meal, exercise or metric record. Unknown and other-user IDs are unavailable.", annotations=@McpTool.McpAnnotations(readOnlyHint=true,destructiveHint=false,idempotentHint=true,openWorldHint=false))
    public Object wellnessGet(
            @McpToolParam(description="meal, exercise or metric",required=true) String entity,
            @McpToolParam(description="Positive owned record ID",required=true) long recordId) {
        scopes.require("prp.wellness.read");
        McpWellnessSupport.table(entity);
        if(recordId<=0) throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Positive record ID required");
        return switch(entity) {
            case "meal" -> wellness.ownedMeal(recordId);
            case "exercise" -> wellness.ownedExercise(recordId);
            default -> wellness.ownedMetric(recordId);
        };
    }

    @McpTool(name="prp_wellness_foods", description="Search public reference foods and your own private foods, up to 30 results. Read only; never edits the public catalog or calls external APIs.", annotations=@McpTool.McpAnnotations(readOnlyHint=true,destructiveHint=false,idempotentHint=true,openWorldHint=false))
    public Object wellnessFoods(@McpToolParam(description="Food name, 1-100 characters",required=true) String query) {
        scopes.require("prp.wellness.read");
        if(query==null || query.isBlank() || query.length()>100) throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Food query required");
        return wellness.foods(query.trim()).stream().limit(30).toList();
    }

    @McpTool(name="prp_prepare_wellness_create", description="Prepare a structured meal, exercise or metric CREATE draft, not a personal note. The input object must contain exactly one of meal, exercise, or metric. For a meal, use mealDate yyyy-MM-dd, mealType BREAKFAST/LUNCH/DINNER/SNACK, note, and items. Catalog foods: item {foodId, grams} ONLY. Estimates: item {name, calories, optional grams} ONLY. Do not supply null placeholders. Saves only a draft, never a health record. After preview, confirm in ChatGPT only if explicitly permitted by the server; otherwise an owner-password approval is required.", annotations=@McpTool.McpAnnotations(readOnlyHint=false,destructiveHint=false,idempotentHint=false,openWorldHint=false))
    public McpDraftService.Preview prepareWellnessCreate(
            @McpToolParam(description="meal, exercise or metric",required=true) String entity,
            @McpToolParam(description="JSON object containing only the matching meal, exercise, or metric object; no user ID and no unnecessary null fields",required=true) Map<String,Object> input) {
        scopes.require("prp.wellness.write.create");
        return drafts.prepareWellnessFromMcp(entity,0,input,McpDraftService.Kind.WELLNESS_CREATE);
    }

    @McpTool(name="prp_prepare_wellness_update", description="Prepare full replacement of one owned meal/exercise/metric. Preview includes before and after. Changed records or catalog nutrition invalidate confirmation. Requires PRP password approval; never updates directly.", annotations=@McpTool.McpAnnotations(readOnlyHint=false,destructiveHint=true,idempotentHint=false,openWorldHint=false))
    public McpDraftService.Preview prepareWellnessUpdate(
            @McpToolParam(description="meal, exercise or metric",required=true) String entity,
            @McpToolParam(description="Positive owned record ID",required=true) long recordId,
            @McpToolParam(description="Full replacement JSON object containing one matching meal, exercise or metric; no null placeholders or owner ID",required=true) Map<String,Object> input) {
        scopes.require("prp.wellness.write.update");
        return drafts.prepareWellnessFromMcp(entity,recordId,input,McpDraftService.Kind.WELLNESS_UPDATE);
    }

    @McpTool(name="prp_prepare_wellness_delete", description="Prepare deletion of one exact owned health record. No deletion occurs until owner approval in PRP and separate confirmation. Any changed record is rejected.", annotations=@McpTool.McpAnnotations(readOnlyHint=false,destructiveHint=true,idempotentHint=false,openWorldHint=false))
    public McpDraftService.Preview prepareWellnessDelete(
            @McpToolParam(description="meal, exercise or metric",required=true) String entity,
            @McpToolParam(description="Positive owned record ID",required=true) long recordId) {
        scopes.require("prp.wellness.write.delete");
        return drafts.prepareWellness(entity,recordId,null,McpDraftService.Kind.WELLNESS_DELETE);
    }

    private McpDraftService.Review healthReview(String draftId) {
        var review=drafts.review(draftId);
        if(!review.kind().startsWith("WELLNESS_")) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Health draft not found");
        return review;
    }

    @McpTool(name="prp_wellness_draft_status", description="Read your own structured health draft status and immutable preview. Only a separately authorized write confirmation can save it.", annotations=@McpTool.McpAnnotations(readOnlyHint=true,destructiveHint=false,idempotentHint=true,openWorldHint=false))
    public McpDraftService.Review wellnessDraftStatus(@McpToolParam(description="Exact health draft UUID",required=true) String draftId) {
        scopes.require("prp.wellness.write.status");
        return healthReview(draftId);
    }

    @McpTool(name="prp_confirm_wellness_draft", description="Commit an owner-approved health draft exactly once. For ChatGPT-authorized WELLNESS_CREATE drafts only, a server-side default-off opt-in permits a PENDING draft after the user explicitly approves the ChatGPT tool confirmation prompt. Never invoke without user confirmation. Update/delete and all other drafts still require PRP password approval. Requires matching OAuth scopes and bound PRP owner. Replays return the existing result.", annotations=@McpTool.McpAnnotations(readOnlyHint=false,destructiveHint=true,idempotentHint=true,openWorldHint=false))
    public McpDraftService.Result confirmWellnessDraft(@McpToolParam(description="Exact health draft UUID",required=true) String draftId) {
        scopes.require("prp.wellness.write.confirm");
        var review=healthReview(draftId);
        scopes.require(McpDraftService.operationScope(review.kind()));
        return drafts.confirm(draftId);
    }

    /**
     * Invoked only by the ChatGPT MCP Apps approval UI. The host must enforce
     * _meta.ui.visibility=["app"]. The server independently enforces verified
     * OAuth owner/client/scopes and the immutable draft state.
     */
    @McpTool(name="prp_chatgpt_wellness_approval",
        description="APP-ONLY: approve or reject the exact pending health CREATE draft after a human clicks the embedded ChatGPT card; never model-visible.",
        annotations=@McpTool.McpAnnotations(readOnlyHint=false,destructiveHint=true,idempotentHint=false,openWorldHint=false))
    public McpDraftService.Approval chatgptWellnessApproval(
            @McpToolParam(description="UUID of the displayed pending health CREATE draft",required=true) String draftId,
            @McpToolParam(description="approve or reject",required=true) String decision) {
        scopes.require("prp.wellness.write.confirm");
        scopes.require("prp.wellness.write.create");
        return drafts.approveFromChatgptUi(draftId, decision);
    }

    private static LocalDate optionalDate(String value) {
        return value == null || value.isBlank() ? null : localDate(value);
    }
    private static LocalDate localDate(String value) {
        try { return LocalDate.parse(value); }
        catch (RuntimeException e) { throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Date must be yyyy-MM-dd"); }
    }
    private static YearMonth yearMonth(String value) {
        try { return YearMonth.parse(value); }
        catch (RuntimeException e) { throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Month must be yyyy-MM"); }
    }
}
