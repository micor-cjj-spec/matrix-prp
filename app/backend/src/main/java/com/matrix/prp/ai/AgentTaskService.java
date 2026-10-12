package com.matrix.prp.ai;

import com.matrix.prp.auth.security.CurrentUser;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class AgentTaskService {
    private static final Set<String> ALLOWED = Set.of("PLAN", "SUMMARIZE", "ANALYZE");
    private final AgentTaskStore store;
    private final OpenClawGatewayClient gateway;
    private final TaskExecutor executor;
    public AgentTaskService(AgentTaskStore store, OpenClawGatewayClient gateway,
                            @Qualifier("aiExecutor") TaskExecutor executor) {
        this.store = store; this.gateway = gateway; this.executor = executor;
    }
    public Map<String, Object> capabilities() {
        return Map.of("openclawEnabled", gateway.configured(), "codexEnabled", false,
            "requiresApproval", true, "mode", "ADMIN_TEXT_ONLY",
            "message", gateway.configured() ? "Isolated Gateway configured; not a live health check"
                : "OpenClaw Gateway disabled until isolated instance is verified");
    }
    public List<AgentTaskStore.AgentTask> list() { return store.list(CurrentUser.id()); }
    public AgentTaskStore.AgentTask find(String id) {
        return store.find(CurrentUser.id(), id)
            .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Agent task not found"));
    }
    public AgentTaskStore.AgentTask create(String type, String prompt) {
        if (!ALLOWED.contains(type))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Unsupported task type");
        String content = prompt == null ? "" : prompt.trim();
        if (content.isBlank() || content.length() > 2000)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Task description must be 1-2000 characters");
        return store.create(CurrentUser.id(), type, content);
    }
    public AgentTaskStore.AgentTask approve(String id, String confirmation) {
        long user = CurrentUser.id();
        if (!"APPROVE_AGENT_TASK".equals(confirmation))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Explicit approval required");
        if (!gateway.configured())
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                "Isolated OpenClaw Gateway is not enabled");
        AgentTaskStore.AgentTask task = find(id);
        if (!store.claim(user, id, user))
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Task already decided");
        try {
            executor.execute(() -> {
                try {
                    String output = gateway.generate(task);
                    store.complete(user, id, output);
                } catch (Exception ex) {
                    // Fail closed and do not attempt automatic replay: agent side effects are unknown.
                    store.fail(user, id, "GATEWAY_ERROR");
                }
            });
        } catch (RuntimeException ex) {
            store.fail(user, id, "WORKER_BUSY");
        }
        return store.find(user, id).orElseThrow();
    }
    public AgentTaskStore.AgentTask cancel(String id) {
        long user = CurrentUser.id();
        find(id);
        if (!store.cancel(user, id))
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Only pending tasks can be cancelled");
        return store.find(user,id).orElseThrow();
    }
}
