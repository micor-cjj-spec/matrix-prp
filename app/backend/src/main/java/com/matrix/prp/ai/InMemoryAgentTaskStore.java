package com.matrix.prp.ai;

import java.time.LocalDateTime;
import java.util.*;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;

@Repository
@Profile("test")
public class InMemoryAgentTaskStore implements AgentTaskStore {
    private final Map<String, AgentTask> all = new HashMap<>();
    private static LocalDateTime now() { return LocalDateTime.now(java.time.Clock.systemUTC()); }
    @Override public synchronized AgentTask create(long user, String type, String prompt) {
        String id = UUID.randomUUID().toString();
        AgentTask task = new AgentTask(id, user, type, prompt, "PENDING_APPROVAL", null,
            null, now(), now(), null, null, "prp:" + user + ":" + id);
        all.put(id, task);
        return task;
    }
    @Override public synchronized Optional<AgentTask> find(long user, String id) {
        AgentTask t = all.get(id);
        return t == null || t.userId() != user ? Optional.empty() : Optional.of(t);
    }
    @Override public synchronized List<AgentTask> list(long user) {
        return all.values().stream().filter(t -> t.userId() == user)
            .sorted(Comparator.comparing(AgentTask::createdAt).reversed()).limit(50).toList();
    }
    @Override public synchronized boolean claim(long user, String id, long approver) {
        Optional<AgentTask> maybe = find(user,id);
        if (maybe.isEmpty() || !maybe.get().status().equals("PENDING_APPROVAL")) return false;
        AgentTask t = maybe.get();
        all.put(id, new AgentTask(id,user,t.taskType(),t.prompt(),"RUNNING",null,null,
            t.createdAt(),now(),approver,now(),t.sessionRef()));
        return true;
    }
    private void change(long user, String id, String required, String status, String result, String code) {
        find(user,id).filter(t -> t.status().equals(required)).ifPresent(t ->
            all.put(id,new AgentTask(id,user,t.taskType(),t.prompt(),status,result,code,
                t.createdAt(),now(),t.approvedBy(),t.approvedAt(),t.sessionRef())));
    }
    @Override public synchronized void complete(long user,String id,String result) {
        change(user,id,"RUNNING","COMPLETED",result,null);
    }
    @Override public synchronized void fail(long user,String id,String code) {
        change(user,id,"RUNNING","FAILED",null,code);
    }
    @Override public synchronized boolean cancel(long user,String id) {
        if (find(user,id).filter(t -> t.status().equals("PENDING_APPROVAL")).isEmpty()) return false;
        change(user,id,"PENDING_APPROVAL","CANCELLED",null,null);
        return true;
    }
}
