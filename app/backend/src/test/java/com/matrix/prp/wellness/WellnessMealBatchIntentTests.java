package com.matrix.prp.wellness;

import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;

class WellnessMealBatchIntentTests {
    private final LocalDate today=LocalDate.of(2026,10,14);

    @Test void splitsTwoMealsAndNeverInventsKcalFromUserEstimate() {
        String text="""
            请帮我记录 2026年10月13日（星期二）的饮食数据：
            午餐（约1450 kcal）
            粉蒸排骨配红薯：约425 kcal
            青椒炒肉：约425 kcal
            肉丸白菜汤：约150 kcal
            白米饭：约265 kcal
            泡萝卜：约35 kcal
            其他烹调油及估算误差补充：约150 kcal
            以上全部吃完，午餐总热量暂按1450 kcal记录。
            晚餐（约105 kcal）
            简爱无糖酸奶135g
            没有吃其他食物
            午餐和晚餐总计1555 kcal。
            """;
        var parsed=WellnessMealBatchIntent.parse(text,today).orElseThrow();
        assertThat(parsed.date()).isEqualTo(LocalDate.of(2026,10,13));
        assertThat(parsed.meals()).hasSize(2);
        assertThat(parsed.meals().get(0).type()).isEqualTo("LUNCH");
        assertThat(parsed.meals().get(0).foods()).hasSize(6);
        assertThat(parsed.meals().get(0).declaredTotal()).isEqualByComparingTo("1450");
        assertThat(parsed.meals().get(0).foods().get(5).calories()).isEqualByComparingTo("150");
        assertThat(parsed.meals().get(1).type()).isEqualTo("DINNER");
        assertThat(parsed.meals().get(1).foods()).hasSize(1);
        assertThat(parsed.meals().get(1).foods().getFirst().name()).isEqualTo("简爱无糖酸奶");
        assertThat(parsed.meals().get(1).foods().getFirst().grams()).isEqualByComparingTo("135");
        assertThat(parsed.meals().get(1).foods().getFirst().calories()).isEqualByComparingTo("105");
    }

    @Test void rejectsMismatchedMealTotalsInsteadOfInventingFood() {
        String text="2026-10-13\n午餐（约1450 kcal）\n饭：100 kcal\n菜：200 kcal\n晚餐（约105 kcal）\n酸奶105g";
        assertThatThrownBy(()->WellnessMealBatchIntent.parse(text,today))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("不一致");
    }

    @Test void rejectsUnspecifiedComponentEnergyInsteadOfInventing() {
        String text="2026-10-13\n午餐（约600 kcal）\n米饭200g\n青椒炒肉300g\n晚餐（约105 kcal）\n酸奶135g";
        assertThatThrownBy(()->WellnessMealBatchIntent.parse(text,today))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("每项热量");
    }

    @Test void neverDropsAnUnparsedFoodLineSilently() {
        String source="2026-10-13\n午餐\n米饭：300 kcal\n鸡蛋\n晚餐（约105 kcal）\n简爱无糖酸奶135g";
        assertThatThrownBy(()->WellnessMealBatchIntent.parse(source,today))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("鸡蛋");
    }

    @Test void oneDinnerWithAttachedSaveInstructionParsesWithoutDroppingFoodOrKcal() {
        String original="晚餐（约105 kcal）\n简爱无糖酸奶135g帮我录人到昨天的晚餐";
        var result=WellnessMealBatchIntent.parse(original,today).orElseThrow();
        assertThat(result.date()).isEqualTo(LocalDate.of(2026,10,13));
        assertThat(result.meals()).hasSize(1);
        var dinner=result.meals().getFirst();
        assertThat(dinner.type()).isEqualTo("DINNER");
        assertThat(dinner.declaredTotal()).isEqualByComparingTo("105");
        assertThat(dinner.foods()).hasSize(1);
        var yogurt=dinner.foods().getFirst();
        assertThat(yogurt.name()).isEqualTo("简爱无糖酸奶");
        assertThat(yogurt.grams()).isEqualByComparingTo("135");
        assertThat(yogurt.calories()).isEqualByComparingTo("105");
    }

    @Test void acceptsCorrectSpellingAndStandardChineseWeightUnits() {
        String source="晚餐（约105千卡）\n简爱无糖酸奶135克，请帮我录入到昨天的晚餐。";
        var meal=WellnessMealBatchIntent.parse(source,today).orElseThrow().meals().getFirst();
        assertThat(meal.foods().getFirst().name()).isEqualTo("简爱无糖酸奶");
        assertThat(meal.foods().getFirst().grams()).isEqualByComparingTo("135");
    }

    @Test void contradictoryMealDestinationIsRejectedInsteadOfSavingBreakfastAsDinner() {
        String source="早餐（约105 kcal）\n简爱无糖酸奶135g帮我录入到昨天的晚餐";
        assertThatThrownBy(()->WellnessMealBatchIntent.parse(source,today))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("餐次标题与记录指令不一致");
    }

    @Test void contradictoryExplicitDateAndRelativeCommandIsRejected() {
        String source="2026-10-12\n晚餐（约105 kcal）\n简爱无糖酸奶135g帮我录入到昨天的晚餐";
        assertThatThrownBy(()->WellnessMealBatchIntent.parse(source,today))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("记录日期与指令日期不一致");
    }

    @Test void matchingExplicitDateInSuffixRemainsSupported() {
        String source="晚餐（约105 kcal）\n简爱无糖酸奶135g帮我录入到2026年10月13日的晚餐";
        var result=WellnessMealBatchIntent.parse(source,today).orElseThrow();
        assertThat(result.date()).isEqualTo(LocalDate.of(2026,10,13));
        assertThat(result.meals()).hasSize(1);
        assertThat(result.meals().getFirst().type()).isEqualTo("DINNER");
    }

    @Test void aCommandCannotConcealAnAdditionalUnparsedFoodOrAlterTheEnergy() {
        String source="晚餐（约105 kcal）\n简爱无糖酸奶135g加一个鸡蛋帮我录入到昨天的晚餐";
        assertThatThrownBy(()->WellnessMealBatchIntent.parse(source,today))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("无法解析餐次明细");
    }

    @Test void noMultiMealIfOnlyOneMealAndRespectsRelativeDates() {
        assertThat(WellnessMealBatchIntent.parse("昨天午餐：米饭 260千卡",today)).isEmpty();
        var two=WellnessMealBatchIntent.parse(
            "昨天\n午餐（约300 kcal）\n米饭：300 kcal\n晚餐（约100 kcal）\n牛奶100g",today).orElseThrow();
        assertThat(two.date()).isEqualTo(today.minusDays(1));
    }
}
