package com.matrix.prp.wellness;

import com.matrix.prp.ai.AiStore;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;

class WellnessChatMealContextTests {
    private static final LocalDate TODAY=LocalDate.of(2026,10,14);
    private static AiStore.Message user(long id,String value){
        return new AiStore.Message(id,"user",value,LocalDateTime.of(2026,10,14,19,0));
    }
    private static AiStore.Message assistant(long id,String value){
        return new AiStore.Message(id,"assistant",value,LocalDateTime.of(2026,10,14,19,0));
    }

    @Test void reusesLatestEstimateButNeverClaimsTheMealWasAlreadySaved(){
        var history=List.of(
            user(1,"今天晚上我吃的楼下炒菜+米饭，饭比较多，炒菜吃的比较少，估算一下热量"),
            assistant(2,"估算热量：约780 kcal。"),
            user(3,"就是5个人点了两荤两素"),
            assistant(4,"按5人两荤两素、饭多菜少，建议记 约650 kcal。"),
            user(5,"帮我录入一下"),
            assistant(6,"没有生成卡片，请手工填写")
        );
        var draft=WellnessChatMealContext.parse(history,TODAY).orElseThrow();
        assertThat(draft.date()).isEqualTo(TODAY);
        assertThat(draft.mealType()).isEqualTo("DINNER");
        assertThat(draft.calories()).isEqualByComparingTo(new BigDecimal("650"));
        assertThat(draft.sourceType()).isEqualTo("AI_ESTIMATE");
        assertThat(draft.foodName()).contains("炒菜","米饭","两荤两素","饭多菜少");
        assertThat(draft.note()).contains("确认前不会入库");
    }

    @Test void withoutCaloriesShowsEditablePreviewInsteadOfInventingOne(){
        var draft=WellnessChatMealContext.parse(List.of(
            user(1,"今天午餐吃了海味馄饨大碗16个"),
            user(2,"帮我录入一下")
        ),TODAY).orElseThrow();
        assertThat(draft.mealType()).isEqualTo("LUNCH");
        assertThat(draft.foodName()).contains("海味馄饨");
        assertThat(draft.calories()).isNull();
    }

    @Test void ignoresAssistantOnlyClaimsAndChoosesLatestUserMeal(){
        assertThat(WellnessChatMealContext.parse(List.of(
            assistant(1,"你吃了米饭，建议记约650 kcal"),
            user(2,"生成一下卡片")
        ),TODAY)).isEmpty();
        var draft=WellnessChatMealContext.parse(List.of(
            user(1,"今天午餐吃了馄饨"),
            assistant(2,"估算热量约650 kcal"),
            user(3,"今天晚餐吃了鸡腿饭"),
            assistant(4,"估算热量：约780 kcal")
        ),TODAY).orElseThrow();
        assertThat(draft.mealType()).isEqualTo("DINNER");
        assertThat(draft.foodName()).contains("鸡腿");
        assertThat(draft.calories()).isEqualByComparingTo("780");
    }


    @Test void latestUnknownDishDoesNotBecomeAnOlderMeal(){
        var draft=WellnessChatMealContext.parse(List.of(
            user(1,"今天午餐吃了米饭"),
            assistant(2,"建议记 500 kcal"),
            user(3,"今晚吃了寿司"),
            assistant(4,"建议记 650 kcal"),
            user(5,"帮我录入一下")
        ),TODAY).orElseThrow();
        assertThat(draft.foodName()).isEqualTo("寿司");
        assertThat(draft.mealType()).isEqualTo("DINNER");
        assertThat(draft.calories()).isEqualByComparingTo("650");
    }

    @Test void tomorrowDinnerKeepsTomorrowAndRejectsUnsupportedAfterTomorrow(){
        var meal=WellnessChatMealContext.parse(List.of(
            user(1,"明天晚餐打算吃米饭"),
            assistant(2,"建议记 600 kcal"),
            user(3,"生成一下卡片")
        ),TODAY).orElseThrow();
        assertThat(meal.date()).isEqualTo(TODAY.plusDays(1));
        assertThat(meal.mealType()).isEqualTo("DINNER");
        assertThat(WellnessChatMealContext.parse(List.of(
            user(1,"后天晚餐打算吃米饭")
        ),TODAY)).isEmpty();
    }

    @Test void screenshotFollowupSelectsRequestedDinnerEvenAfterLunchDiscussion(){
        var draft=WellnessChatMealContext.parse(List.of(
            user(1,"今天晚上我吃的楼下炒菜+米饭，饭比较多，炒菜吃的比较少"),
            assistant(2,"估算热量：约780 kcal"),
            user(3,"就是5个人点了两荤两素"),
            assistant(4,"建议记 约650 kcal"),
            user(5,"今天午餐吃了海味馄饨大碗16个"),
            assistant(6,"建议记约720 kcal"),
            user(7,"帮我创建一下卡片我录入今天的晚餐")
        ),TODAY,"帮我创建一下卡片我录入今天的晚餐").orElseThrow();
        assertThat(draft.date()).isEqualTo(TODAY);
        assertThat(draft.mealType()).isEqualTo("DINNER");
        assertThat(draft.calories()).isEqualByComparingTo("650");
        assertThat(draft.foodName()).contains("米饭","两荤两素");
    }

    @Test void explicitlyRequestedMealCannotSilentlyFallBackToLunch(){
        assertThat(WellnessChatMealContext.parse(List.of(
            user(1,"今天午餐吃了馄饨"),assistant(2,"建议记650 kcal")
        ),TODAY,"帮我生成今天晚餐的卡片")).isEmpty();
    }

    @Test void selectsYesterdayDinnerEvenWhenTodayDinnerIsMoreRecent(){
        var history=List.of(
            user(1,"昨天晚上吃了米饭"),assistant(2,"建议记600 kcal"),
            user(3,"今晚吃了炒菜"),assistant(4,"建议记700 kcal")
        );
        var yesterday=WellnessChatMealContext.parse(
            history,TODAY,"生成昨天晚餐卡片").orElseThrow();
        assertThat(yesterday.date()).isEqualTo(TODAY.minusDays(1));
        assertThat(yesterday.foodName()).contains("米饭");
        assertThat(yesterday.calories()).isEqualByComparingTo("600");
        var lastNight=WellnessChatMealContext.parse(
            history,TODAY,"生成昨晚晚餐卡片").orElseThrow();
        assertThat(lastNight.date()).isEqualTo(TODAY.minusDays(1));
        assertThat(lastNight.calories()).isEqualByComparingTo("600");
    }

    @Test void tomorrowSynonymsConstrainCalendarDate(){
        var history=List.of(user(1,"明天早餐吃了面包"),
            assistant(2,"建议记200 kcal"),
            user(3,"今天早餐吃了鸡蛋"),
            assistant(4,"建议记150 kcal"));
        var tomorrow=WellnessChatMealContext.parse(
            history,TODAY,"明早早餐生成卡片").orElseThrow();
        assertThat(tomorrow.date()).isEqualTo(TODAY.plusDays(1));
        assertThat(tomorrow.foodName()).contains("面包");
    }

    @Test void requestedDateCannotRewriteAnOlderMeal(){
        assertThat(WellnessChatMealContext.parse(List.of(
            user(1,"昨天晚餐吃了米饭"),assistant(2,"建议记650 kcal")
        ),TODAY,"帮我生成今天晚餐的卡片")).isEmpty();
    }

    @Test void lateUnrelatedMealEstimateCannotContaminateAnOlderDinner(){
        var dinner=WellnessChatMealContext.parse(List.of(
            user(1,"今晚吃了米饭"),assistant(2,"建议记600 kcal"),
            user(3,"午餐吃了馄饨"),assistant(4,"建议记900 kcal")
        ),TODAY,"晚餐生成卡片").orElseThrow();
        assertThat(dinner.calories()).isEqualByComparingTo("600");
    }

    @Test void userExplicitCaloriesTakePrecedenceOverAssistantSuggestion(){
        var draft=WellnessChatMealContext.parse(List.of(
            user(1,"2026-10-14 晚餐吃了米饭炒菜 700 kcal"),
            assistant(2,"建议记 900 kcal")
        ),TODAY).orElseThrow();
        assertThat(draft.sourceType()).isEqualTo("USER_ESTIMATE");
        assertThat(draft.calories()).isEqualByComparingTo("700");
    }
}
