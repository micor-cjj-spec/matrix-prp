package com.matrix.prp.wellness;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.common.api.ResourceNotFoundException;
import com.matrix.prp.wellness.WellnessModels.Meal;
import com.matrix.prp.wellness.WellnessModels.MealItem;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class WellnessNutritionDetailsServiceTests {
    @AfterEach void clearIdentity() { SecurityContextHolder.clearContext(); }

    private void asUser(long id) {
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken(
                        new UserProfile(id, "owner", "Owner"), null, List.of()));
    }

    @Test void oldMealsHaveEmptyEnrichmentAndPartialMacroCoverage() {
        asUser(101L);
        JdbcTemplate db = mock(JdbcTemplate.class);
        WellnessService wellness = mock(WellnessService.class);
        Meal meal = new Meal(5L, LocalDate.parse("2026-11-12"), "LUNCH", null, List.of(
                new MealItem(12L, 2L, "鸡蛋", new BigDecimal("100"),
                        new BigDecimal("144"), new BigDecimal("13.3"),
                        new BigDecimal("2.8"), new BigDecimal("8.8"), true),
                new MealItem(13L, 0L, "烧牛肉", BigDecimal.ZERO,
                        new BigDecimal("470"), null, null, null, true)));
        when(wellness.ownedMeal(5L)).thenReturn(meal);
        when(db.query(anyString(), any(RowMapper.class), eq(5L), eq(101L)))
                .thenReturn(List.of());

        var details = new WellnessNutritionDetailsService(db, wellness,
                new ObjectMapper()).readOwnedMeal(5L);

        assertThat(details.meal()).isEqualTo(meal);
        assertThat(details.analyses()).isEmpty();
        assertThat(details.nutrients()).isEmpty();
        assertThat(details.nutritionCompleteness().foodCount()).isEqualTo(2);
        assertThat(details.nutritionCompleteness().knownProteinCount()).isEqualTo(1);
        assertThat(details.nutritionCompleteness().knownCarbsCount()).isEqualTo(1);
        assertThat(details.nutritionCompleteness().knownFatCount()).isEqualTo(1);
        verify(db).query(startsWith("SELECT a.id"), any(RowMapper.class), eq(5L), eq(101L));
        verify(db).query(startsWith("SELECT n.*"), any(RowMapper.class), eq(5L), eq(101L));
        verify(db, never()).update(anyString(), any(Object[].class));
    }

    @Test void crossAccountMealFailsBeforeAnyEnrichmentQuery() {
        asUser(102L);
        JdbcTemplate db = mock(JdbcTemplate.class);
        WellnessService wellness = mock(WellnessService.class);
        when(wellness.ownedMeal(5L))
                .thenThrow(new ResourceNotFoundException("Meal not found"));
        var service = new WellnessNutritionDetailsService(db, wellness, new ObjectMapper());

        assertThatThrownBy(() -> service.readOwnedMeal(5L))
                .isInstanceOf(ResourceNotFoundException.class);
        verifyNoInteractions(db);
    }

    @Test void rejectsInvalidMealIdWithoutQueryingDatabase() {
        JdbcTemplate db = mock(JdbcTemplate.class);
        WellnessService wellness = mock(WellnessService.class);
        var service = new WellnessNutritionDetailsService(db, wellness, new ObjectMapper());

        assertThatThrownBy(() -> service.readOwnedMeal(0L))
                .isInstanceOf(IllegalArgumentException.class);
        verifyNoInteractions(db, wellness);
    }
}
