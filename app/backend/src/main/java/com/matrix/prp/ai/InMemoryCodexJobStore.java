package com.matrix.prp.ai;

import java.time.LocalDateTime;
import java.util.*;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;

@Repository
@Profile("test")
public class InMemoryCodexJobStore implements CodexJobStore {
    private final Map<String,Job> all = new HashMap<>();
    private static LocalDateTime now() { return LocalDateTime.now(java.time.Clock.systemUTC()); }
    @Override public synchronized Job create(long user, String repository, String type, String prompt) {
        String id = UUID.randomUUID().toString();
        Job job = new Job(id,user,repository,type,prompt,"PENDING_APPROVAL",null,null,null,now(),now());
        all.put(id,job);
        return job;
    }
    @Override public synchronized Optional<Job> find(long user,String id) {
        Job job = all.get(id);
        return job == null || job.userId()!=user ? Optional.empty() : Optional.of(job);
    }
    @Override public synchronized List<Job> list(long user) {
        return all.values().stream().filter(j -> j.userId()==user)
            .sorted(Comparator.comparing(Job::createdAt).reversed()).limit(50).toList();
    }
    @Override public synchronized boolean claim(long user,String id,long approver) {
        var job = find(user,id).orElse(null);
        if (job==null || !job.status().equals("PENDING_APPROVAL")) return false;
        all.put(id,new Job(id,user,job.repository(),job.taskType(),job.prompt(),"DISPATCHING",
            null,approver,now(),job.createdAt(),now()));
        return true;
    }
    private void change(long user,String id,String expected,String target,String code) {
        find(user,id).filter(j -> j.status().equals(expected)).ifPresent(j ->
            all.put(id,new Job(id,user,j.repository(),j.taskType(),j.prompt(),target,code,
                j.approvedBy(),j.approvedAt(),j.createdAt(),now())));
    }
    @Override public synchronized void dispatched(long user,String id) {
        change(user,id,"DISPATCHING","DISPATCHED",null);
    }
    @Override public synchronized void fail(long user,String id,String code) {
        change(user,id,"DISPATCHING","FAILED",code);
    }
    @Override public synchronized boolean cancel(long user,String id) {
        if(find(user,id).filter(j -> j.status().equals("PENDING_APPROVAL")).isEmpty()) return false;
        change(user,id,"PENDING_APPROVAL","CANCELLED",null);
        return true;
    }
}
