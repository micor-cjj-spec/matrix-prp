package com.matrix.prp.ai;

import com.fasterxml.jackson.databind.JsonNode;
import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.finance.model.FinanceTransactionFilter;
import com.matrix.prp.finance.service.FinanceService;
import com.matrix.prp.practice.PracticeService;
import com.matrix.prp.tasks.model.TaskFilter;
import com.matrix.prp.tasks.service.TaskService;
import com.matrix.prp.wellness.WellnessService;
import java.time.LocalDate;
import java.time.YearMonth;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

/** Read-only allowlisted business adapters; never execute SQL, arbitrary URLs or write operations. */
@Component
public class AiToolRegistry {
    public record Definition(String name, String scope, String description, Map<String,Object> parameters) {}
    public record Result(Object data, AiStore.MessageBlock card) {}
    private final TaskService tasks;
    private final ObjectProvider<PracticeService> practice;
    private final ObjectProvider<WellnessService> wellness;
    private final FinanceService finance;
    private final AiNavigationResolver navigation;

    public AiToolRegistry(TaskService tasks, ObjectProvider<PracticeService> practice,
                          ObjectProvider<WellnessService> wellness, FinanceService finance,
                          AiNavigationResolver navigation) {
        this.tasks = tasks; this.practice = practice; this.wellness = wellness;
        this.finance = finance; this.navigation = navigation;
    }
    private static Map<String,Object> schema(Map<String,Object> properties) {
        return Map.of("type","object", "properties", properties, "additionalProperties",false);
    }
    private static Map<String,Object> field(String type, String description) {
        return Map.of("type",type,"description",description);
    }
    public List<Definition> definitions(Set<String> scopes) {
        List<Definition> result = new ArrayList<>();
        if (scopes.contains("tasks")) result.add(new Definition("tasks_list","tasks",
            "查询当前用户的任务列表，可按状态与日期筛选，至多返回20条",
            schema(Map.of("status",field("string","todo/in_progress/done 等状态，可留空"),
                "date",field("string","yyyy-MM-dd，指定任务截止日期，可留空")))));
        if (scopes.contains("practice")) result.add(new Definition("practice_statistics","practice",
            "获取当前用户刷题累计、正确和错误数量", schema(Map.of())));
        if (scopes.contains("wellness")) result.add(new Definition("wellness_daily","wellness",
            "获取当前用户指定日期饮食与运动汇总，不包含体重和病历",
            schema(Map.of("date",field("string","yyyy-MM-dd；缺省为今天")))));
        if (scopes.contains("finance")) result.add(new Definition("finance_monthly","finance",
            "获取当前用户某个月的收支汇总、分类及最多10条账目，不包含备注",
            schema(Map.of("month",field("string","yyyy-MM；缺省为当前月")))));
        result.add(new Definition("navigation_open","", "提供 PRP 应用内的可点击入口，不直接控制浏览器",
            schema(Map.of("module",Map.of("type","string","enum",navigation.modules().stream().sorted().toList()),
                "recordId",field("integer","仅任务模块可选，必须是当前用户拥有的任务编号"),
                "date",field("string","仅健康模块可选，yyyy-MM-dd"),
                "month",field("string","仅财务模块可选，yyyy-MM")))));
        return result;
    }
    public String scopeOf(String name) {
        return switch (name) {
            case "tasks_list" -> "tasks";
            case "practice_statistics" -> "practice";
            case "wellness_daily" -> "wellness";
            case "finance_monthly" -> "finance";
            case "navigation_open" -> "";
            default -> throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Unknown AI tool");
        };
    }
    public Result execute(String name, JsonNode args, Set<String> scopes) {
        CurrentUser.id(); // Requires server-established security context; never accepts a userId from the model.
        String required = scopeOf(name);
        if (!required.isEmpty() && !scopes.contains(required))
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Tool scope not approved");
        if (args == null || !args.isObject() || args.size() > 5)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Malformed tool arguments");
        return switch (name) {
            case "tasks_list" -> {
                String status = optional(args,"status");
                String when = optional(args,"date");
                LocalDate due = when == null ? null : LocalDate.parse(when);
                var items = tasks.listLimited(new TaskFilter(status, null, due, null), 20).stream()
                    .map(t -> Map.of("id",t.id(),"title",t.title(),"status",t.status(),
                        "priority",t.priority(),"dueDate",t.dueDate()==null?"":t.dueDate().toString())).toList();
                yield new Result(Map.of("items",items,"returned",items.size(),"limit",20),
                    navigation.resolve("tasks",null));
            }
            case "practice_statistics" -> {
                var service = practice.getIfAvailable();
                if (service == null) throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "Practice unavailable");
                var stats=service.statistics();
                yield new Result(Map.of("attempted",stats.attempted(),"correct",stats.correct(),"wrong",stats.wrong()),
                    navigation.resolve("practice",null));
            }
            case "wellness_daily" -> {
                var service = wellness.getIfAvailable();
                if (service == null) throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "Wellness unavailable");
                String when=optional(args,"date");
                LocalDate date=when==null?LocalDate.now():LocalDate.parse(when);
                var day=service.daily(date);
                Map<String,Object> data=new LinkedHashMap<>();
                data.put("date",date.toString()); data.put("caloriesKcal",day.calories());
                data.put("proteinGrams",day.proteinG()); data.put("carbsGrams",day.carbsG());
                data.put("fatGrams",day.fatG()); data.put("mealCount",day.mealCount());
                data.put("exerciseMinutes",day.exerciseMinutes());
                yield new Result(data,navigation.resolve("wellness",null));
            }
            case "finance_monthly" -> {
                String when=optional(args,"month");
                YearMonth month=when==null?YearMonth.now():YearMonth.parse(when);
                var filter=new FinanceTransactionFilter(month,null,null);
                var summary=finance.monthlySummary(filter);
                var categories=finance.monthlyCategorySummary(new FinanceTransactionFilter(month,"expense",null))
                    .stream().limit(10).map(c->Map.of("category",c.category(),"amount",c.amount().toString())).toList();
                var transactions=finance.listTransactionsLimited(filter, 10).stream()
                    .map(t->Map.of("date",t.transactionDate().toString(),"type",t.type(),
                        "amount",t.amount().toString(),"category",t.category())).toList();
                yield new Result(Map.of("month",month.toString(),"income",summary.income().toString(),
                    "expense",summary.expense().toString(),"balance",summary.balance().toString(),
                    "categories",categories,"transactions",transactions,"limit",10),
                    navigation.resolve("finance",null));
            }
            case "navigation_open" -> {
                String module=optional(args,"module");
                if (module==null) throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Module required");
                var card=navigation.resolve(module,args);
                yield new Result(Map.of("route",card.route(),"label",card.label()),card);
            }
            default -> throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Unknown AI tool");
        };
    }
    private static String optional(JsonNode args,String key) {
        JsonNode value=args.get(key);
        if (value==null || value.isNull()) return null;
        if (!value.isTextual() || value.asText().length()>50)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid tool field: "+key);
        String text=value.asText().trim();
        return text.isEmpty()?null:text;
    }
}
