package com.matrix.prp;

import com.matrix.prp.notification.ReminderSchedule;
import java.time.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ReminderScheduleTests {
 @Test void weekdaySkipsWeekend(){
   var friday=Instant.parse("2026-10-09T13:00:00Z");
   assertEquals(Instant.parse("2026-10-12T12:00:00Z"),
     ReminderSchedule.next("WEEKDAYS","Asia/Shanghai","20:00","",null,null,friday));
 }
 @Test void onceMustBeInFuture(){
   var now=Instant.parse("2026-10-10T07:00:00Z");
   assertThrows(RuntimeException.class,()->ReminderSchedule.next("ONCE","Asia/Shanghai",null,null,null,now,now));
 }
 @Test void selectedWeekday(){
   assertEquals(Instant.parse("2026-10-14T11:00:00Z"),
     ReminderSchedule.next("WEEKLY","Asia/Shanghai","19:00","3",null,null,Instant.parse("2026-10-10T07:00:00Z")));
 }
 @Test void monthlyLastDay(){
   assertEquals(Instant.parse("2026-11-30T12:00:00Z"),
     ReminderSchedule.next("MONTHLY","Asia/Shanghai","20:00","",31,null,Instant.parse("2026-11-01T00:00:00Z")));
 }
}

