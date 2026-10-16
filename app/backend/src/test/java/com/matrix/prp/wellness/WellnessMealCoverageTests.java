package com.matrix.prp.wellness;

import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.wellness.WellnessModels.Profile;
import java.sql.ResultSet;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class WellnessMealCoverageTests {
    @AfterEach void clear() { SecurityContextHolder.clearContext(); }

    @Test void reportsOnlyUnrecordedSlotsOnCompletedDaysForAuthenticatedOwner() throws Exception {
        long owner = 501L;
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(new UserProfile(owner,"owner","Owner"),null,List.of()));
        JdbcTemplate db = mock(JdbcTemplate.class);
        WellnessService service = spy(new WellnessService(db));
        doReturn(new Profile(null,"Asia/Shanghai")).when(service).profile();
        LocalDate yesterday = LocalDate.now(ZoneId.of("Asia/Shanghai")).minusDays(1);
        doAnswer(inv -> {
            RowCallbackHandler handler = inv.getArgument(1);
            ResultSet row = mock(ResultSet.class);
            when(row.getObject("meal_date",LocalDate.class)).thenReturn(yesterday);
            when(row.getString("meal_type")).thenReturn("BREAKFAST","SNACK","BREAKFAST");
            handler.processRow(row);
            handler.processRow(row);
            handler.processRow(row);
            return null;
        }).when(db).query(startsWith("SELECT meal_date,meal_type FROM prp_wellness_meals"),
            any(RowCallbackHandler.class),eq(owner),eq(yesterday.minusDays(6)),eq(yesterday));
        var result = service.mealCoverage(7);
        assertThat(result).hasSize(7);
        assertThat(result.getFirst().date()).isEqualTo(yesterday);
        assertThat(result.getFirst().recordedMealTypes()).containsExactly("BREAKFAST","SNACK");
        assertThat(result.getFirst().missingMealTypes()).containsExactly("LUNCH","DINNER");
        assertThat(result.getFirst().savedMealCount()).isEqualTo(3);
        assertThat(result.get(1).recordedMealTypes()).isEmpty();
        assertThat(result.get(1).missingMealTypes()).containsExactly("BREAKFAST","LUNCH","DINNER");
        verify(db).query(startsWith("SELECT meal_date,meal_type FROM prp_wellness_meals"),
            any(RowCallbackHandler.class),eq(owner),eq(yesterday.minusDays(6)),eq(yesterday));
        verify(db,never()).update(anyString(),any(Object[].class));
    }

    @Test void rejectsUnboundedQueriesBeforeReadingDatabase() {
        JdbcTemplate db = mock(JdbcTemplate.class);
        WellnessService service = new WellnessService(db);
        assertThatThrownBy(() -> service.mealCoverage(31))
            .isInstanceOf(IllegalArgumentException.class);
        verifyNoInteractions(db);
    }
}
