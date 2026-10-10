package com.matrix.prp.notification;

import java.time.*;
import java.util.List;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.scheduling.annotation.EnableScheduling;

@Component
@Profile("!test")
@EnableScheduling
public class NotificationScheduler {
    private final NotificationService service;
    private final NotificationDelivery delivery;
    private final JdbcTemplate jdbc;
    public NotificationScheduler(NotificationService service,NotificationDelivery delivery,JdbcTemplate jdbc){
       this.service=service;this.delivery=delivery;this.jdbc=jdbc;
    }
    @Scheduled(fixedDelay=30000)
    public void tick(){
      for(long id:service.dueRules()){
          try{service.fire(id);}catch(Exception e){org.slf4j.LoggerFactory.getLogger(getClass()).warn("Notification rule failed: {}",id,e);}
      }
      // Recover a send interrupted by a process crash; delivery remains at-least-once.
      jdbc.update("UPDATE prp_notification_deliveries SET status='RETRY',next_attempt_at=? WHERE status='SENDING' AND updated_at<?",
          ReminderSchedule.utc(Instant.now()),ReminderSchedule.utc(Instant.now().minusSeconds(120)));
      List<Long> ids=jdbc.queryForList("SELECT id FROM prp_notification_deliveries WHERE status IN ('PENDING','RETRY') AND next_attempt_at<=? ORDER BY id LIMIT 50",Long.class,ReminderSchedule.utc(Instant.now()));
      for(long id:ids){try{delivery.dispatch(id);}catch(Exception e){org.slf4j.LoggerFactory.getLogger(getClass()).warn("Push attempt failed for delivery {}",id,e);}}
    }
}

