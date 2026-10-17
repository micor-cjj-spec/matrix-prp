package com.matrix.prp.ai;

import com.fasterxml.jackson.databind.JsonNode;
import com.matrix.prp.tasks.service.TaskService;
import java.time.LocalDate;
import java.time.YearMonth;
import java.util.Map;
import java.util.Set;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

/** Only first-party, registered routes may be emitted by an LLM. */
@Component
public class AiNavigationResolver {
    private static final Map<String, String> ROUTES = Map.of(
        "tasks", "/tasks", "wellness", "/wellness", "finance", "/finance",
        "practice", "/practice", "records", "/records", "videos", "/videos",
        "knowledge", "/knowledge", "apps", "/apps", "vocal", "/vocal");
    private final TaskService tasks;
    public AiNavigationResolver(TaskService tasks) { this.tasks = tasks; }

    public AiStore.MessageBlock resolve(String module, JsonNode arguments) {
        String route = ROUTES.get(module);
        if (route == null) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Unregistered application route");
        if (arguments != null && arguments.hasNonNull("recordId")) {
            if (!module.equals("tasks") || !arguments.get("recordId").canConvertToLong()
                    || arguments.get("recordId").asLong() <= 0)
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Unsupported record navigation");
            long id = arguments.get("recordId").asLong();
            if (tasks.list().stream().noneMatch(task -> task.id() == id))
                throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Record not found");
            route += "?focus=" + id;
        }
        if (arguments != null && arguments.hasNonNull("date")) {
            if (!module.equals("wellness"))
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Date filter unavailable");
            LocalDate date = LocalDate.parse(arguments.get("date").asText());
            route += "?date=" + date;
        }
        if (arguments != null && arguments.hasNonNull("month")) {
            if (!module.equals("finance"))
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Month filter unavailable");
            YearMonth month = YearMonth.parse(arguments.get("month").asText());
            route += "?month=" + month;
        }
        return new AiStore.MessageBlock(0, "navigation", module, LABELS.get(module), route);
    }

    private static final Map<String, String> LABELS = Map.of(
        "tasks", "打开任务", "wellness", "打开健康", "finance", "打开财务",
        "practice", "打开刷题", "records", "打开笔记", "videos", "打开视频学习",
        "knowledge", "打开知识库", "apps", "打开应用中心", "vocal", "打开声乐训练");
    public Set<String> modules() { return ROUTES.keySet(); }
}
