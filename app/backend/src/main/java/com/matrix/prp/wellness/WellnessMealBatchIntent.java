package com.matrix.prp.wellness;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * Parses multi-meal notes ONLY when the user wrote the serving energy explicitly.
 * AI generated calories are never a trusted substitute for this evidence.
 */
final class WellnessMealBatchIntent {
    record Food(String name, BigDecimal grams, BigDecimal calories) {}
    record Meal(String type, BigDecimal declaredTotal, List<Food> foods) {}
    record Batch(LocalDate date, List<Meal> meals) {}
    private static final Pattern ISO_DATE=Pattern.compile("(?<!\\d)(20\\d{2})-(\\d{2})-(\\d{2})(?!\\d)");
    private static final Pattern CN_DATE=Pattern.compile("(?<!\\d)(20\\d{2})年(\\d{1,2})月(\\d{1,2})日");
    private static final Pattern HEADER=Pattern.compile(
        "^(早餐|早饭|午餐|午饭|晚餐|晚饭|加餐)\\s*(?:[（(]\\s*约?\\s*(\\d+(?:\\.\\d{1,2})?)\\s*(?:kcal|千卡|大卡|卡路里)\\s*[）)])?\\s*[:：]?$",
        Pattern.CASE_INSENSITIVE);
    private static final Pattern FOOD_ENERGY=Pattern.compile(
        "^(?:[-*•]\\s*)?(.{1,120}?)\\s*[:：]\\s*约?\\s*(\\d+(?:\\.\\d{1,2})?)\\s*(?:kcal|千卡|大卡|卡路里)\\s*$",
        Pattern.CASE_INSENSITIVE);
    private static final Pattern GRAMS=Pattern.compile("(?i)^(.{1,120}?)\\s*(\\d+(?:\\.\\d)?)\\s*(?:g|克)(?:\\s*[（(].*[）)])?$");
    private static final Set<String> TYPES=Set.of("BREAKFAST","LUNCH","DINNER","SNACK");

    private WellnessMealBatchIntent() {}

    static Optional<Batch> parse(String input,LocalDate today){
        if(input==null || input.isBlank() || input.length()>1500)return Optional.empty();
        LocalDate date=today;
        try{
            var iso=ISO_DATE.matcher(input);
            var chinese=CN_DATE.matcher(input);
            if(iso.find()) date=LocalDate.of(Integer.parseInt(iso.group(1)),
                Integer.parseInt(iso.group(2)),Integer.parseInt(iso.group(3)));
            else if(chinese.find())date=LocalDate.of(Integer.parseInt(chinese.group(1)),
                Integer.parseInt(chinese.group(2)),Integer.parseInt(chinese.group(3)));
            else if(input.contains("前天"))date=today.minusDays(2);
            else if(input.contains("昨天"))date=today.minusDays(1);
        }catch(Exception e){ throw new IllegalArgumentException("无效的饮食记录日期"); }
        if(date.isAfter(today.plusDays(1)) || date.isBefore(today.minusYears(2)))
            throw new IllegalArgumentException("日期超出可记录范围");
        var meals=new ArrayList<Meal>();
        String type=null;
        BigDecimal declared=null;
        List<Food> foods=new ArrayList<>();
        for(String raw:input.split("\\R")){
            String line=raw.strip();
            var header=HEADER.matcher(line);
            if(header.matches()){
                if(type!=null)meals.add(finish(type,declared,foods));
                type=type(header.group(1));
                declared=header.group(2)==null?null:new BigDecimal(header.group(2));
                foods=new ArrayList<>();
                continue;
            }
            if(type==null || line.isBlank() || line.contains("总计") ||
                line.contains("总热量") || line.contains("没有吃其他") ||
                line.startsWith("以上") || line.startsWith("全部") ||
                line.startsWith("当日"))continue;
            var food=FOOD_ENERGY.matcher(line);
            if(food.matches()){
                String name=food.group(1).strip();
                BigDecimal kcal=new BigDecimal(food.group(2));
                if(kcal.signum()<=0 || kcal.compareTo(new BigDecimal("20000"))>0 || name.length()>120)
                    throw new IllegalArgumentException("单项食物热量或名称不合法");
                var grams=GRAMS.matcher(name);
                BigDecimal weight=BigDecimal.ZERO;
                if(grams.matches()){
                    name=grams.group(1).strip();
                    weight=new BigDecimal(grams.group(2));
                }
                foods.add(new Food(name,weight,kcal));
            } else {
                var grams=GRAMS.matcher(line);
                if(grams.matches()){
                    // One-item meal declared total can supply the per-event kcal at finish().
                    foods.add(new Food(grams.group(1).strip(),new BigDecimal(grams.group(2)),null));
                } else {
                    // Do not silently drop a named food such as "鸡蛋" just because
                    // the user omitted grams/kcal. Ask for correction before saving.
                    throw new IllegalArgumentException("无法解析餐次明细："+line+"；请为食物补充本次热量");
                }
            }
        }
        if(type!=null)meals.add(finish(type,declared,foods));
        if(meals.size()<2 || meals.size()>4)return Optional.empty();
        Set<String> seen=new LinkedHashSet<>();
        for(Meal meal:meals)
            if(!TYPES.contains(meal.type()) || !seen.add(meal.type()))
                throw new IllegalArgumentException("重复或不合法的餐次，请逐项核对");
        return Optional.of(new Batch(date,List.copyOf(meals)));
    }

    private static Meal finish(String type,BigDecimal declared,List<Food> raw){
        if(raw.isEmpty() || raw.size()>8)
            throw new IllegalArgumentException("餐次中缺少可确认的食物明细（最多8项）");
        List<Food> foods=new ArrayList<>();
        for(Food food:raw){
            BigDecimal kcal=food.calories();
            if(kcal==null && raw.size()==1)kcal=declared;
            if(kcal==null || kcal.signum()<=0 || kcal.compareTo(new BigDecimal("20000"))>0)
                throw new IllegalArgumentException("多餐记录必须提供每项热量；单项餐次可以提供合计热量");
            if(food.grams().signum()<0 || food.grams().compareTo(new BigDecimal("3000"))>0)
                throw new IllegalArgumentException("食物克重不合法");
            foods.add(new Food(food.name(),food.grams(),kcal));
        }
        BigDecimal sum=foods.stream().map(Food::calories).reduce(BigDecimal.ZERO,BigDecimal::add);
        if(declared!=null && sum.subtract(declared).abs().compareTo(new BigDecimal("0.01"))>0)
            throw new IllegalArgumentException(type+" 餐次热量合计与各项热量不一致，请先核对");
        if(sum.compareTo(new BigDecimal("20000"))>0)
            throw new IllegalArgumentException("餐次总热量超出范围");
        return new Meal(type,declared==null?sum:declared,List.copyOf(foods));
    }

    private static String type(String zh){
        return switch(zh){
            case "早餐","早饭"->"BREAKFAST";
            case "午餐","午饭"->"LUNCH";
            case "晚餐","晚饭"->"DINNER";
            case "加餐"->"SNACK";
            default->throw new IllegalArgumentException("Unknown meal type");
        };
    }
}
