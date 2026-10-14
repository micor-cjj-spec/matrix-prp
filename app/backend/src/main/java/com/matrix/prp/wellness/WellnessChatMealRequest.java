package com.matrix.prp.wellness;

import java.util.regex.Pattern;

/**
 * Only classifies short explicit draft/card follow-ups. Real food entries
 * still go through the standard structured parser / nutrition validation.
 */
final class WellnessChatMealRequest {
    private static final Pattern ACTION=Pattern.compile(
        "创建|生成|制作|做|出|整理|准备|弄|填写|录入|录人|记录|保存|记一下");
    private static final Pattern CARD=Pattern.compile("卡片|草稿|健康记录|饮食记录|餐食记录");
    private static final Pattern MEAL=Pattern.compile(
        "早餐|早饭|午餐|午饭|晚餐|晚饭|今晚|早上|中午|晚上|加餐|夜宵|这顿|这餐|饮食|健康|食物");
    private static final Pattern FOOD=Pattern.compile(
        "米饭|炒菜|炒肉|馄饨|混沌|米线|鸡腿|面条|鸡蛋|牛奶|酸奶|土豆|面包|豆腐|青菜|排骨|饺子|饭团|寿司|羊肉|烧烤|牛肉|米粉|粥");
    private static final Pattern TECH=Pattern.compile(
        "如何|怎么|为什么|代码|接口|组件|页面|需求|设计|开发|实现|测试|报错|修复|日志|任务|会议|笔记|备忘");
    private WellnessChatMealRequest() {}

    static boolean isContextualFollowup(String text) {
        if(text==null)return false;
        String message=text.strip();
        if(message.isEmpty() || message.length()>180 || TECH.matcher(message).find())
            return false;
        boolean action=ACTION.matcher(message).find();
        if(!action)return false;
        boolean hasCard=CARD.matcher(message).find();
        boolean mealReference=MEAL.matcher(message).find();
        if(!hasCard && !mealReference &&
            !message.matches("(?s).*?(?:帮我|给我|请|麻烦).{0,18}(?:录入|录人|记录|保存|记一下).*"))
            return false;
        // A sentence describing an actual food is not a reference to a previous
        // meal, even if the food is unknown. Never attach the previous meal to it.
        if(message.matches("(?s).*(?:吃了|吃的|喝了|点了|吃过|买了).{1,80}.*"))
            return false;
        if(FOOD.matcher(message).find())return false;
        return hasCard || mealReference || message.matches("(?s).*(?:录入|录人|记录|保存|记一下).*");
    }
}
