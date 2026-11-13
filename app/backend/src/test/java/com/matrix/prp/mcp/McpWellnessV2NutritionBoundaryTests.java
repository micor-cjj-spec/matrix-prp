package com.matrix.prp.mcp;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.finance.service.FinanceService;
import com.matrix.prp.records.service.RecordService;
import com.matrix.prp.tasks.service.TaskService;
import com.matrix.prp.wellness.WellnessModels;
import com.matrix.prp.wellness.WellnessService;
import jakarta.validation.Validator;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.server.ResponseStatusException;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

/**
 * H2-005 contract: reuse the current scoped 9-tool wellness surface.
 * Model-proposed screenshot/OCR data is NOT the same as a confirmed meal,
 * and a model cannot promote nutrition-label candidates to write input.
 */
class McpWellnessV2NutritionBoundaryTests {
    private PrpMcpTools tools(WellnessService wellness, McpDraftService drafts,
                              McpScopeGuard scopes) {
        return new PrpMcpTools(mock(TaskService.class), mock(FinanceService.class),
                wellness, mock(RecordService.class), drafts, scopes);
    }

    @Test void oneOwnedMealReadKeepsUnknownMacrosNullWithoutExposingRawSourceEvidence() {
        WellnessService wellness = mock(WellnessService.class);
        McpDraftService drafts = mock(McpDraftService.class);
        McpScopeGuard scopes = mock(McpScopeGuard.class);
        var meal = new WellnessModels.Meal(57L, LocalDate.of(2026,11,13),"LUNCH",null,
            List.of(new WellnessModels.MealItem(58L,0L,"外卖水饺",BigDecimal.ZERO,
                new BigDecimal("460"),null,null,null,true)));
        when(wellness.ownedMeal(57L)).thenReturn(meal);

        var result = tools(wellness,drafts,scopes).wellnessGet("meal",57L);
        assertThat(result).isSameAs(meal);
        assertThat(((WellnessModels.Meal) result).items().getFirst().proteinG()).isNull();
        assertThat(((WellnessModels.Meal) result).items().getFirst().grams())
                .isEqualByComparingTo("0");
        verify(scopes).require("prp.wellness.read");
        verify(wellness).ownedMeal(57L);
        verifyNoInteractions(drafts);
    }

    @Test void dailySummaryPreservesUnknownMacroTotals() {
        WellnessService wellness = mock(WellnessService.class);
        McpScopeGuard scopes = mock(McpScopeGuard.class);
        LocalDate date = LocalDate.of(2026,11,13);
        var summary = new WellnessModels.DailySummary(date,new BigDecimal("460"),
                null,null,null,1,0,BigDecimal.ZERO,null,null,List.of("LUNCH"));
        when(wellness.daily(date)).thenReturn(summary);

        var result = tools(wellness,mock(McpDraftService.class),scopes)
                .wellnessDaily("2026-11-13");
        assertThat(result).isSameAs(summary);
        assertThat(((WellnessModels.DailySummary) result).proteinG()).isNull();
        verify(scopes).require("prp.wellness.read");
    }

    @Test void missingReadScopeCannotReachUserMealData() {
        WellnessService wellness = mock(WellnessService.class);
        McpScopeGuard scopes = mock(McpScopeGuard.class);
        doThrow(new McpScopeGuard.MissingScope("prp.wellness.read"))
                .when(scopes).require("prp.wellness.read");
        var tools = tools(wellness,mock(McpDraftService.class),scopes);

        assertThatThrownBy(()->tools.wellnessGet("meal",57L))
                .isInstanceOf(McpScopeGuard.MissingScope.class);
        verifyNoInteractions(wellness);
    }

    @Test void modelCannotSubmitUnreviewedOrderOrLabelFieldsAsMcpMealInput() {
        var support = new McpWellnessSupport(mock(JdbcTemplate.class),
                mock(WellnessService.class),new ObjectMapper(),mock(Validator.class));
        Map<String,Object> labelCandidate = Map.of(
                "labelPer100gCandidate",Map.of("proteinG",new BigDecimal("3.2")),
                "sourceContext",Map.of("kind","NUTRITION_LABEL"));
        Map<String,Object> item=Map.of(
                "name","盒装牛奶","calories",new BigDecimal("130"),
                "grams",new BigDecimal("250"),
                "labelPer100gCandidate",labelCandidate);
        Map<String,Object> request=Map.of("meal",Map.of(
                "mealDate","2026-11-13","mealType","BREAKFAST",
                "note","confirmed food only","items",List.of(item)));

        assertThatThrownBy(()->support.fromMcpInput("meal",request))
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(ex->assertThat(((ResponseStatusException)ex).getStatusCode())
                        .isEqualTo(HttpStatus.BAD_REQUEST));
    }

    @Test void wellnessCreateRemainsDraftOnlyAndRequiresWriteScope() {
        WellnessService wellness = mock(WellnessService.class);
        McpDraftService drafts = mock(McpDraftService.class);
        McpScopeGuard scopes = mock(McpScopeGuard.class);
        Map<String,Object> request=Map.of("meal",Map.of(
                "mealDate","2026-11-13","mealType","LUNCH",
                "items",List.of(Map.of("name","水饺","calories",460))));

        tools(wellness,drafts,scopes).prepareWellnessCreate("meal",request);
        verify(scopes).require("prp.wellness.write.create");
        verify(drafts).prepareWellnessFromMcp(eq("meal"),eq(0L),
                same(request),eq(McpDraftService.Kind.WELLNESS_CREATE));
        verifyNoInteractions(wellness); // Preparing is not a business write.
    }
}
