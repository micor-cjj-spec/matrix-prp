package com.matrix.prp.activity;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;
@Component
@Profile("test")
public class InMemoryActivityLogStore implements ActivityLogStore {
    private final Map<Long,List<Entry>> data=new ConcurrentHashMap<>();
    @Override public void recordHttp(long userId,String method,String route,int status,long ms) {
        data.computeIfAbsent(userId,id->java.util.Collections.synchronizedList(new ArrayList<>()))
            .add(new Entry("HTTP",method+" "+route,Integer.toString(status),status,
                Math.max(0,ms),LocalDateTime.now(Clock.systemUTC())));
    }
    @Override public List<Entry> recent(long userId,int days,int limit) {
        List<Entry> rows=data.get(userId);
        if(rows==null) return List.of();
        LocalDateTime since=LocalDateTime.now(Clock.systemUTC()).minusDays(days);
        synchronized(rows) {
            return rows.stream().filter(e->!e.occurredAt().isBefore(since))
                .sorted(Comparator.comparing(Entry::occurredAt).reversed()).limit(limit).toList();
        }
    }
}
