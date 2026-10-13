package com.matrix.prp.ai;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.finance.service.FinanceService;
import com.matrix.prp.practice.PracticeService;
import com.matrix.prp.tasks.service.TaskService;
import com.matrix.prp.wellness.WellnessModels;
import com.matrix.prp.wellness.WellnessService;
import java.math.BigDecimal;
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

class AiWellnessToolTests {
    private final ObjectMapper json=new ObjectMapper();
    @AfterEach void cleanup(){SecurityContextHolder.clearContext();}
    @SuppressWarnings("unchecked")
    @Test void separatesDietScopeFromBodyMeasurementsAndCapsRange() throws Exception {
        SecurityContextHolder.getContext().setAuthentication(new UsernamePasswordAuthenticationToken(
            new UserProfile(77L,"owner","Owner"),null,List.of()));
        ObjectProvider<WellnessService> wellness=mock(ObjectProvider.class);
        WellnessService service=mock(WellnessService.class);
        when(wellness.getIfAvailable()).thenReturn(service);
        LocalDate day=LocalDate.of(2026,10,13);
        when(service.trends(7)).thenReturn(List.of(
            new WellnessModels.TrendPoint(day,new BigDecimal("1150"),20,new BigDecimal("80.3")),
            new WellnessModels.TrendPoint(day.minusDays(1),null,null,null)));
        AiToolRegistry tools=new AiToolRegistry(mock(TaskService.class),
            mock(ObjectProvider.class),wellness,mock(FinanceService.class),
            new AiNavigationResolver(mock(TaskService.class)));
        assertThat(tools.definitions(Set.of("wellness")).stream().map(AiToolRegistry.Definition::name).toList())
            .contains("wellness_trends").doesNotContain("wellness_body_trends");
        assertThatThrownBy(()->tools.execute("wellness_body_trends",json.readTree("{}"),Set.of("wellness")))
            .isInstanceOf(ResponseStatusException.class);
        var diet=tools.execute("wellness_trends",json.readTree("{\"days\":7}"),Set.of("wellness"));
        String data=json.writeValueAsString(diet.data());
        assertThat(data).contains("1150").contains("nullMeansUnrecorded").doesNotContain("80.3");
        assertThatThrownBy(()->tools.execute("wellness_trends",json.readTree("{\"days\":90}"),Set.of("wellness")))
            .isInstanceOf(ResponseStatusException.class);
        var body=tools.execute("wellness_body_trends",json.readTree("{}"),Set.of("wellness_body"));
        assertThat(json.writeValueAsString(body.data())).contains("80.3").doesNotContain("1150");
        verify(service,times(2)).trends(7);
    }
}
