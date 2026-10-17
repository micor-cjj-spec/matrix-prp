package com.matrix.prp.activity;
import java.time.LocalDateTime;
import java.util.List;
/** Tenant-owned structured metadata; no bodies, tokens or raw server logs. */
public interface ActivityLogStore {
    record Entry(String kind,String action,String status,Integer httpStatus,long elapsedMs,LocalDateTime occurredAt) {}
    void recordHttp(long userId,String method,String route,int status,long elapsedMs);
    List<Entry> recent(long userId,int days,int limit);
}
