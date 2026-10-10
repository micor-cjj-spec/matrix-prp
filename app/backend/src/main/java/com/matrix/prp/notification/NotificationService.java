package com.matrix.prp.notification;

import com.matrix.prp.auth.security.CurrentUser;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.*;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import java.sql.Statement;

@Service
@Profile("!test")
public class NotificationService {
    private final JdbcTemplate jdbc;
    public NotificationService(JdbcTemplate jdbc) { this.jdbc=jdbc; }

    public record RuleRequest(String title, String body, String category, String scheduleType,
                              String timezone, String localTime, String weekdays, Integer monthDay, Instant onceAt) {}
    public record SubscriptionRequest(String endpoint, String p256dh, String auth, String deviceName) {}

    private static String required(String text, int max) {
        if (text==null || text.isBlank() || text.length()>max) throw ReminderSchedule.bad("Required text is empty or too long");
        return text.trim();
    }
    private static String category(String text) {
        String result=(text==null || text.isBlank())?"CUSTOM":text.trim();
        if (!result.matches("[A-Za-z_]{1,32}")) throw ReminderSchedule.bad("Invalid category");
        return result;
    }
    private record Prepared(String title,String body,String category,String type,String zone,
                            String time,String days,Integer month,LocalDateTime once,LocalDateTime next) {}
    private Prepared prepare(RuleRequest r) {
        String title=required(r.title(),120), body=required(r.body(),500);
        String zone=required(r.timezone(),64), type=required(r.scheduleType(),16).toUpperCase();
        String time="ONCE".equals(type)?null:required(r.localTime(),8);
        String days="WEEKLY".equals(type)?required(r.weekdays(),24):"";
        Instant next=ReminderSchedule.next(type,zone,time,days,r.monthDay(),r.onceAt(),Instant.now());
        return new Prepared(title,body,category(r.category()),type,zone,time,days,
            r.monthDay(),r.onceAt()==null?null:ReminderSchedule.utc(r.onceAt()),ReminderSchedule.utc(next));
    }
    public List<Map<String,Object>> rules() {
        return jdbc.queryForList("SELECT id,title,body,category,schedule_type AS scheduleType,timezone,local_time AS localTime,weekdays,month_day AS monthDay,next_fire_at AS nextFireAt,enabled FROM prp_notification_rules WHERE user_id=? ORDER BY id DESC LIMIT 200",CurrentUser.id());
    }
    public long create(RuleRequest r) {
        var p=prepare(r); long user=CurrentUser.id(); var now=ReminderSchedule.utc(Instant.now());
        var key=new GeneratedKeyHolder();
        jdbc.update(c->{var ps=c.prepareStatement("INSERT INTO prp_notification_rules (user_id,title,body,category,schedule_type,timezone,local_time,weekdays,month_day,once_at,next_fire_at,enabled,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?)",Statement.RETURN_GENERATED_KEYS);
          ps.setLong(1,user);ps.setString(2,p.title());ps.setString(3,p.body());ps.setString(4,p.category());ps.setString(5,p.type());ps.setString(6,p.zone());ps.setString(7,p.time());ps.setString(8,p.days());if(p.month()==null)ps.setNull(9,java.sql.Types.TINYINT);else ps.setInt(9,p.month());ps.setObject(10,p.once());ps.setObject(11,p.next());ps.setObject(12,now);ps.setObject(13,now);return ps;},key);
        return key.getKey().longValue();
    }
    public void update(long id,RuleRequest r) {
        var p=prepare(r);
        int changed=jdbc.update("UPDATE prp_notification_rules SET title=?,body=?,category=?,schedule_type=?,timezone=?,local_time=?,weekdays=?,month_day=?,once_at=?,next_fire_at=?,enabled=1,updated_at=? WHERE id=? AND user_id=?",
          p.title(),p.body(),p.category(),p.type(),p.zone(),p.time(),p.days(),p.month(),p.once(),p.next(),ReminderSchedule.utc(Instant.now()),id,CurrentUser.id());
        if(changed==0) throw notFound();
    }
    public void status(long id, boolean enabled) {
        long user=CurrentUser.id();
        List<Map<String,Object>> rows=jdbc.queryForList("SELECT schedule_type AS type,timezone,local_time AS time,weekdays,month_day AS month,once_at AS onceAt FROM prp_notification_rules WHERE id=? AND user_id=?",id,user);
        if(rows.isEmpty()) throw notFound();
        Map<String,Object> row=rows.get(0);
        LocalDateTime next=null;
        if(enabled){
           Instant once=row.get("onceAt")==null?null:((LocalDateTime)row.get("onceAt")).toInstant(ZoneOffset.UTC);
           next=ReminderSchedule.utc(ReminderSchedule.next((String)row.get("type"),(String)row.get("timezone"),
             (String)row.get("time"),(String)row.get("weekdays"),(Integer)row.get("month"),once,Instant.now()));
        }
        jdbc.update("UPDATE prp_notification_rules SET enabled=?,next_fire_at=?,updated_at=? WHERE id=? AND user_id=?",enabled?1:0,next,ReminderSchedule.utc(Instant.now()),id,user);
    }
    public void delete(long id) {
        // Detach historical messages before deleting a rule.
        if(jdbc.update("DELETE FROM prp_notification_rules WHERE id=? AND user_id=?",id,CurrentUser.id())==0) throw notFound();
    }
    public List<Map<String,Object>> inbox(){
        return jdbc.queryForList("SELECT id,title,body,category,created_at AS createdAt,read_at AS readAt FROM prp_notification_messages WHERE user_id=? ORDER BY id DESC LIMIT 100",CurrentUser.id());
    }
    public void markRead(long id) {
        if(jdbc.update("UPDATE prp_notification_messages SET read_at=COALESCE(read_at,?) WHERE id=? AND user_id=?",ReminderSchedule.utc(Instant.now()),id,CurrentUser.id())==0) throw notFound();
    }
    @Transactional
    public long sendTest() { return enqueue(CurrentUser.id(),null,null,"Matrix PRP 测试通知","设备推送已连接，欢迎使用消息与提醒中心！","SYSTEM"); }
    @Transactional
    public long sendNow(RuleRequest r) {
        return enqueue(CurrentUser.id(),null,null,required(r.title(),120),required(r.body(),500),category(r.category()));
    }
    long enqueue(long user,Long rule,LocalDateTime scheduled,String title,String body,String kind){
        var key=new GeneratedKeyHolder();
        jdbc.update(c->{var ps=c.prepareStatement("INSERT INTO prp_notification_messages (user_id,rule_id,scheduled_for,title,body,category,created_at) VALUES (?,?,?,?,?,?,?)",Statement.RETURN_GENERATED_KEYS);
           ps.setLong(1,user);if(rule==null)ps.setNull(2,java.sql.Types.BIGINT);else ps.setLong(2,rule);
           ps.setObject(3,scheduled);ps.setString(4,title);ps.setString(5,body);ps.setString(6,kind);ps.setObject(7,ReminderSchedule.utc(Instant.now()));return ps;},key);
        long id=key.getKey().longValue();
        jdbc.update("INSERT IGNORE INTO prp_notification_deliveries (message_id,subscription_id,status,next_attempt_at,updated_at) SELECT ?,id,'PENDING',?,? FROM prp_push_subscriptions WHERE user_id=?",
            id,ReminderSchedule.utc(Instant.now()),ReminderSchedule.utc(Instant.now()),user);
        return id;
    }
    @Transactional
    public void fire(long id){
        var list=jdbc.queryForList("SELECT id,user_id,title,body,category,schedule_type,timezone,local_time,weekdays,month_day,once_at,next_fire_at FROM prp_notification_rules WHERE id=? AND enabled=1 AND next_fire_at<=?",id,ReminderSchedule.utc(Instant.now()));
        if(list.isEmpty()) return;
        var row=list.get(0); var due=(LocalDateTime)row.get("next_fire_at");
        String type=(String)row.get("schedule_type");
        LocalDateTime next=null;
        if(!"ONCE".equals(type)){
            next=ReminderSchedule.utc(ReminderSchedule.next(type,(String)row.get("timezone"),(String)row.get("local_time"),
               (String)row.get("weekdays"),(Integer)row.get("month_day"),null,due.toInstant(ZoneOffset.UTC)));
        }
        int changed=jdbc.update("UPDATE prp_notification_rules SET next_fire_at=?,enabled=?,updated_at=? WHERE id=? AND enabled=1 AND next_fire_at=?",
            next,"ONCE".equals(type)?0:1,ReminderSchedule.utc(Instant.now()),id,due);
        if(changed==1) enqueue(((Number)row.get("user_id")).longValue(),id,due,(String)row.get("title"),(String)row.get("body"),(String)row.get("category"));
    }
    public List<Long> dueRules(){
        return jdbc.queryForList("SELECT id FROM prp_notification_rules WHERE enabled=1 AND next_fire_at<=? ORDER BY next_fire_at LIMIT 100",Long.class,ReminderSchedule.utc(Instant.now()));
    }
    public String subscribe(SubscriptionRequest r){
        String endpoint=required(r.endpoint(),2048), key=required(r.p256dh(),512),auth=required(r.auth(),256);
        URI uri;try{uri=URI.create(endpoint);}catch(Exception e){throw ReminderSchedule.bad("Invalid Push endpoint");}
        String host=uri.getHost()==null?"":uri.getHost().toLowerCase();
        boolean validHost=List.of("push.apple.com","mozilla.com","googleapis.com","notify.windows.com")
           .stream().anyMatch(s->host.equals(s)||host.endsWith("."+s));
        if(!"https".equals(uri.getScheme()) || uri.getUserInfo()!=null || uri.getPort()!=-1 || !validHost)
           throw ReminderSchedule.bad("Unsupported Push provider");
        if(!key.matches("[A-Za-z0-9_\\-+/=]{20,512}") || !auth.matches("[A-Za-z0-9_\\-+/=]{8,256}"))
           throw ReminderSchedule.bad("Invalid subscription keys");
        String hash;try{hash=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(endpoint.getBytes(StandardCharsets.UTF_8)));}
        catch(Exception e){throw new IllegalStateException(e);}
        jdbc.update("INSERT INTO prp_push_subscriptions (user_id,endpoint_hash,endpoint,p256dh,auth_secret,device_name,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?) ON DUPLICATE KEY UPDATE user_id=VALUES(user_id),p256dh=VALUES(p256dh),auth_secret=VALUES(auth_secret),device_name=VALUES(device_name),updated_at=VALUES(updated_at)",
          CurrentUser.id(),hash,endpoint,key,auth, r.deviceName()==null?"浏览器":r.deviceName().substring(0,Math.min(100,r.deviceName().length())),ReminderSchedule.utc(Instant.now()),ReminderSchedule.utc(Instant.now()));
        return "subscribed";
    }
    public void unsubscribe(long id){
        if(jdbc.update("DELETE FROM prp_push_subscriptions WHERE id=? AND user_id=?",id,CurrentUser.id())==0) throw notFound();
    }
    public List<Map<String,Object>> devices(){
        return jdbc.queryForList("SELECT id,device_name AS deviceName,created_at AS createdAt FROM prp_push_subscriptions WHERE user_id=? ORDER BY id DESC",CurrentUser.id());
    }
    private static ResponseStatusException notFound(){return new ResponseStatusException(HttpStatus.NOT_FOUND,"Resource not found");}
}

