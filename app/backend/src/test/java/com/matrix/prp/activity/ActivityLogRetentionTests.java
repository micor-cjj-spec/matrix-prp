package com.matrix.prp.activity;

import java.time.LocalDateTime;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

/** Cleanup must be bounded even when a large stale backlog exists. */
class ActivityLogRetentionTests {
    @Test void stopsAfterShortBatch() {
        JdbcTemplate jdbc=mock(JdbcTemplate.class);
        when(jdbc.update(startsWith("DELETE FROM prp_api_request_log"),any(LocalDateTime.class)))
            .thenReturn(5000,12);
        new JdbcActivityLogStore(jdbc).purgeExpired();
        verify(jdbc,times(2)).update(startsWith("DELETE FROM prp_api_request_log"),any(LocalDateTime.class));
    }

    @Test void stopsAtFiveFullBatches() {
        JdbcTemplate jdbc=mock(JdbcTemplate.class);
        when(jdbc.update(startsWith("DELETE FROM prp_api_request_log"),any(LocalDateTime.class)))
            .thenReturn(5000);
        new JdbcActivityLogStore(jdbc).purgeExpired();
        verify(jdbc,times(5)).update(startsWith("DELETE FROM prp_api_request_log"),any(LocalDateTime.class));
    }
}
