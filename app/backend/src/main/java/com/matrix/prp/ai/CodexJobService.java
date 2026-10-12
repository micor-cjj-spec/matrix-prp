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
public class CodexJobService {
    private static final Set<String> ALLOWED = Set.of("IMPLEMENT","FIX","TESTS");
    public record Detail(CodexJobStore.Job job, CodexWorkflowClient.Run execution) {}
    private final CodexJobStore store;
    private final CodexWorkflowClient workflow;
    private final TaskExecutor executor;

    public CodexJobService(CodexJobStore store,CodexWorkflowClient workflow,
            @Qualifier("aiExecutor") TaskExecutor executor) {
        this.store=store;this.workflow=workflow;this.executor=executor;
    }
    public Map<String,Object> capabilities() {
        return Map.of("enabled",workflow.configured(),"repository",CodexWorkflowClient.REPOSITORY,
            "workflow",CodexWorkflowClient.WORKFLOW,"requiresApproval",true,
            "execution","GITHUB_HOSTED_EPHEMERAL",
            "note","Approval dispatches a workflow; GitHub Actions secrets and permissions must be configured separately");
    }
    public CodexJobStore.Job create(String type,String prompt) {
        if(!ALLOWED.contains(type)) throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Unsupported Codex task type");
        String content=prompt==null?"":prompt.trim();
        if(content.isEmpty() || content.length()>1500)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Codex task length must be 1-1500 characters");
        return store.create(CurrentUser.id(),CodexWorkflowClient.REPOSITORY,type,content);
    }
    public List<CodexJobStore.Job> list() { return store.list(CurrentUser.id()); }
    public CodexJobStore.Job find(String id) {
        return store.find(CurrentUser.id(),id)
            .orElseThrow(()->new ResponseStatusException(HttpStatus.NOT_FOUND,"Codex request not found"));
    }
    public Detail detail(String id) {
        CodexJobStore.Job job=find(id);
        CodexWorkflowClient.Run run=job.status().equals("DISPATCHED") ? workflow.status(job):null;
        return new Detail(job,run);
    }
    public CodexJobStore.Job approve(String id,String confirmation) {
        long owner=CurrentUser.id();
        if(!"APPROVE_CODEX_JOB".equals(confirmation))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Explicit Codex approval required");
        if(!workflow.configured())
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,"Codex workflow is not enabled");
        CodexJobStore.Job job=find(id);
        if(!store.claim(owner,id,owner))
            throw new ResponseStatusException(HttpStatus.CONFLICT,"Codex request already decided");
        try {
            executor.execute(()->{
                try {
                    workflow.dispatch(job);
                    store.dispatched(owner,id);
                } catch(Exception ignored) {
                    // Dispatch may have reached GitHub despite a network failure: never replay automatically.
                    store.fail(owner,id,"DISPATCH_UNCERTAIN");
                }
            });
        } catch(RuntimeException rejected) {
            store.fail(owner,id,"WORKER_BUSY");
        }
        return store.find(owner,id).orElseThrow();
    }
    public CodexJobStore.Job cancel(String id) {
        long owner=CurrentUser.id();
        find(id);
        if(!store.cancel(owner,id))
            throw new ResponseStatusException(HttpStatus.CONFLICT,"Only pending Codex requests can be cancelled");
        return store.find(owner,id).orElseThrow();
    }
}
