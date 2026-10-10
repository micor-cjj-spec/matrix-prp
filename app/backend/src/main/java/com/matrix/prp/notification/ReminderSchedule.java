package com.matrix.prp.notification;

import java.time.*;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

/** Recurrence calculation is always done in the user's timezone, then persisted in UTC. */
public final class ReminderSchedule {
    private ReminderSchedule() {}
    public static LocalDateTime utc(Instant time) { return LocalDateTime.ofInstant(time, ZoneOffset.UTC); }
    public static Set<Integer> days(String days) {
        if (days == null || days.isBlank()) return Set.of();
        try {
            Set<Integer> result = Arrays.stream(days.split(",")).map(Integer::parseInt).collect(Collectors.toSet());
            if (result.stream().anyMatch(d -> d < 1 || d > 7)) throw new IllegalArgumentException();
            return result;
        } catch (IllegalArgumentException ex) { throw bad("Weekdays must be 1-7 (Monday-Sunday)"); }
    }
    static ResponseStatusException bad(String message) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, message);
    }
    public static Instant next(String type, String zone, String clock, String days, Integer monthDay,
                               Instant once, Instant after) {
        ZoneId tz;
        try { tz = ZoneId.of(zone); } catch (Exception ex) { throw bad("Invalid IANA time zone"); }
        if ("ONCE".equals(type)) {
            if (once == null || !once.isAfter(after)) throw bad("One-time reminder must be in the future");
            return once;
        }
        LocalTime time;
        try { time = LocalTime.parse(clock); } catch (Exception ex) { throw bad("Invalid reminder time, use HH:mm"); }
        Set<Integer> weekdays = days(days);
        if (!Set.of("DAILY","WEEKDAYS","WEEKLY","MONTHLY").contains(type))
            throw bad("Invalid schedule type");
        if ("WEEKLY".equals(type) && weekdays.isEmpty()) throw bad("Choose at least one weekday");
        if ("MONTHLY".equals(type) && (monthDay == null || monthDay < 1 || monthDay > 31))
            throw bad("Month day must be 1-31");
        LocalDate start = after.atZone(tz).toLocalDate();
        for (int i=0; i<400; i++) {
            LocalDate day = start.plusDays(i);
            int dow = day.getDayOfWeek().getValue();
            if ("WEEKDAYS".equals(type) && dow > 5) continue;
            if ("WEEKLY".equals(type) && !weekdays.contains(dow)) continue;
            if ("MONTHLY".equals(type) && day.getDayOfMonth() != Math.min(monthDay, day.lengthOfMonth())) continue;
            Instant candidate = ZonedDateTime.of(day,time,tz).toInstant();
            if (candidate.isAfter(after)) return candidate;
        }
        throw bad("Unable to calculate next reminder");
    }
}

