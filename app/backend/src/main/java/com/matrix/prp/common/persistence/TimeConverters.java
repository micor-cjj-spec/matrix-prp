package com.matrix.prp.common.persistence;

import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;

public final class TimeConverters {

    private static final ZoneId SYSTEM_ZONE = ZoneId.systemDefault();

    private TimeConverters() {
    }

    public static OffsetDateTime toOffsetDateTime(LocalDateTime value) {
        return value == null ? null : value.atZone(SYSTEM_ZONE).toOffsetDateTime();
    }

    public static LocalDateTime toLocalDateTime(OffsetDateTime value) {
        return value == null ? null : value.atZoneSameInstant(SYSTEM_ZONE).toLocalDateTime();
    }
}
