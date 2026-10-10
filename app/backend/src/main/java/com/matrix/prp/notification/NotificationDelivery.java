package com.matrix.prp.notification;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.security.Security;
import java.time.*;
import java.util.List;
import java.util.Map;
import nl.martijndwars.webpush.Notification;
import nl.martijndwars.webpush.PushService;
import nl.martijndwars.webpush.Utils;
import org.bouncycastle.jce.provider.BouncyCastleProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
@Profile("!test")
public class NotificationDelivery {
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;
    private final String vapidPublic,vapidPrivate;
    public NotificationDelivery(JdbcTemplate jdbc,ObjectMapper mapper,
         @Value("${MATRIX_PRP_VAPID_PUBLIC_KEY:}") String pub,@Value("${MATRIX_PRP_VAPID_PRIVATE_KEY:}") String priv){
        this.jdbc=jdbc;this.mapper=mapper;this.vapidPublic=pub;this.vapidPrivate=priv;
    }
    void dispatch(long deliveryId){
      // Do not claim deliveries when VAPID is not configured. Inbox remains available.
      if(vapidPublic.isBlank() || vapidPrivate.isBlank()) return;
      var now=ReminderSchedule.utc(Instant.now());
      int taken=jdbc.update("UPDATE prp_notification_deliveries SET status='SENDING',attempts=attempts+1,updated_at=? WHERE id=? AND status IN ('PENDING','RETRY') AND next_attempt_at<=?",now,deliveryId,now);
      if(taken==0)return;
      var rows=jdbc.queryForList("SELECT d.attempts,s.endpoint,s.p256dh,s.auth_secret,m.title,m.body FROM prp_notification_deliveries d JOIN prp_push_subscriptions s ON s.id=d.subscription_id JOIN prp_notification_messages m ON m.id=d.message_id AND m.user_id=s.user_id WHERE d.id=?",deliveryId);
      if(rows.isEmpty()){jdbc.update("UPDATE prp_notification_deliveries SET status='FAILED',updated_at=? WHERE id=?",now,deliveryId);return;}
      var row=rows.get(0);
      try {
          if(Security.getProvider("BC")==null)Security.addProvider(new BouncyCastleProvider());
          PushService push=new PushService();
          push.setPublicKey(Utils.loadPublicKey(vapidPublic));
          push.setPrivateKey(Utils.loadPrivateKey(vapidPrivate));
          byte[] json=mapper.writeValueAsBytes(Map.of("title",row.get("title"),"body",row.get("body"),"url","/notifications"));
          Notification notification=new Notification((String)row.get("endpoint"),(String)row.get("p256dh"),(String)row.get("auth_secret"),json);
          var response=push.send(notification);
          int status=response.getStatusLine().getStatusCode();
          if(status>=200 && status<300){
              jdbc.update("UPDATE prp_notification_deliveries SET status='SENT',updated_at=? WHERE id=?",ReminderSchedule.utc(Instant.now()),deliveryId);
          } else if(status==404 || status==410){
              jdbc.update("DELETE FROM prp_push_subscriptions WHERE endpoint=?",(String)row.get("endpoint"));
          } else {retry(deliveryId,((Number)row.get("attempts")).intValue());}
      } catch(Exception e){
          retry(deliveryId,((Number)row.get("attempts")).intValue());
      }
    }
    private void retry(long id,int attempts){
        String status=attempts>=5?"FAILED":"RETRY";
        long delay=Math.min(3600L,30L*(1L<<Math.min(attempts,7)));
        jdbc.update("UPDATE prp_notification_deliveries SET status=?,next_attempt_at=?,updated_at=? WHERE id=?",
            status,ReminderSchedule.utc(Instant.now().plusSeconds(delay)),ReminderSchedule.utc(Instant.now()),id);
    }
}

