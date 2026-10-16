package com.matrix.prp.ai;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.finance.service.FinanceService;
import com.matrix.prp.practice.PracticeService;
import com.matrix.prp.tasks.service.TaskService;
import com.matrix.prp.wellness.WellnessService;
import java.time.LocalDate;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

class AiMealCoverageTests {
    @AfterEach void clear() { SecurityContextHolder.clearContext(); }

    @SuppressWarnings("unchecked")
    @Test void availableOnlyAfterWellnessScopeAndReturnsReadOnlyResults() throws Exception {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(new UserProfile(502L,"reader","Reader"),null,List.of()));
        TaskService task = mock(TaskService.class);
        ObjectProvider<PracticeService> practice = mock(ObjectProvider.class);
        ObjectProvider<WellnessService> wellness = mock(ObjectProvider.class);
        WellnessService service = mock(WellnessService.class);
        when(wellness.getIfAvailable()).thenReturn(service);
        when(service.mealCoverage(7)).thenReturn(List.of(
            new WellnessService.MealCoverageDay(LocalDate.of(2026,10,15),
                List.of("BREAKFAST"),List.of("LUNCH","DINNER"),1)));
        var registry = new AiToolRegistry(task,practice,wellness,mock(FinanceService.class),
            new AiNavigationResolver(task));
        assertThat(registry.definitions(Set.of()).stream().map(AiToolRegistry.Definition::name))
            .doesNotContain("wellness_meal_coverage");
        assertThat(registry.definitions(Set.of("wellness")).stream().map(AiToolRegistry.Definition::name))
            .contains("wellness_meal_coverage");
        var args = new ObjectMapper().readTree("{}");
        assertThatThrownBy(() -> registry.execute("wellness_meal_coverage",args,Set.of()))
            .isInstanceOf(ResponseStatusException.class);
        verifyNoInteractions(service);
        var result = registry.execute("wellness_meal_coverage",args,Set.of("wellness"));
        assertThat(result.card().route()).isEqualTo("/wellness");
        assertThat(result.data().toString()).contains("missingSlotCount=2");
        verify(service).mealCoverage(7);
        assertThatThrownBy(() -> registry.execute("wellness_meal_coverage",
            new ObjectMapper().readTree("{\"days\":365}"),Set.of("wellness")))
            .isInstanceOf(ResponseStatusException.class);
        verify(service,times(1)).mealCoverage(anyInt());
    }

    @Test void naturalLanguageGapQueriesChooseBoundedTool() {
        assertThat(AiService.mealCoverageIntent("帮我查一下，我有哪几次的用餐情况没有录入")).isTrue();
        assertThat(AiService.mealCoverageIntent("请列出最近30天没有录入的晚餐")).isTrue();
        assertThat(AiService.mealCoverageIntent("帮我记录今天午餐的米饭")).isFalse();
        assertThat(AiService.coverageDays("近14天有哪些午餐未录入")).isEqualTo(14);
        assertThat(AiService.coverageDays("一个月里有哪些饭没录入")).isEqualTo(30);
        assertThat(AiService.coverageDays("哪几次用餐没录入")).isEqualTo(7);
    }
}
