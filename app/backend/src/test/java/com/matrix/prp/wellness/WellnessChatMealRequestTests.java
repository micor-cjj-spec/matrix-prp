package com.matrix.prp.wellness;

import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;

class WellnessChatMealRequestTests {
    @Test void screenshotRequestAlwaysUsesContextInsteadOfFoodOnlyModel(){
        assertThat(WellnessChatMealRequest.isContextualFollowup(
            "帮我创建一下卡片我录入今天的晚餐")).isTrue();
        assertThat(WellnessChatMealRequest.isContextualFollowup("生成一下卡片")).isTrue();
        assertThat(WellnessChatMealRequest.isContextualFollowup("帮我录入一下")).isTrue();
        assertThat(WellnessChatMealRequest.isContextualFollowup("请记录今天的晚餐")).isTrue();
        assertThat(WellnessChatMealRequest.isContextualFollowup("晚餐也帮我录入")).isTrue();
        assertThat(WellnessChatMealRequest.isContextualFollowup("帮我生成今天晚餐的记录卡片")).isTrue();
    }
    @Test void fullFoodDescriptionsAndDeveloperQuestionsCannotReuseOlderFood(){
        assertThat(WellnessChatMealRequest.isContextualFollowup(
            "今晚吃了寿司，帮我生成卡片")).isFalse();
        assertThat(WellnessChatMealRequest.isContextualFollowup(
            "我吃了米饭和炒菜，帮我记录晚餐")).isFalse();
        assertThat(WellnessChatMealRequest.isContextualFollowup(
            "怎么开发健康记录卡片组件")).isFalse();
        assertThat(WellnessChatMealRequest.isContextualFollowup(
            "帮我记录一条日志")).isFalse();
    }
}
