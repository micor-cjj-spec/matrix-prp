package com.matrix.prp.wellness;

import com.matrix.prp.ai.AiStore;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.Optional;
import java.util.regex.Pattern;

/**
 * Builds an editable draft suggestion from the owner's CURRENT conversation.
 * Model-authored calories are only suggestions; they cannot write health data.
 */
final class WellnessChatMealContext {
    record Candidate(LocalDate date, String mealType, String foodName,
                     BigDecimal calories, String sourceType, String note, String sourceText) {}
    record ListedFood(String name, BigDecimal grams) {}
    private static final Pattern ENERGY=Pattern.compile(
        "(?iu)(?:建议记|建议记录|建议录入|推荐记录|估算热量|热量)\\s*[:：]?\\s*(?:约|大约)?\\s*(\\d{1,4}(?:\\.\\d{1,2})?)\\s*(?:kcal|千卡|大卡)");
    private static final Pattern ISO=Pattern.compile("(?<!\\d)(20\\d{2}-\\d{2}-\\d{2})(?!\\d)");
    private static final Pattern CHINESE=Pattern.compile("(?<!\\d)(20\\d{2})年(\\d{1,2})月(\\d{1,2})日");
    private static final Pattern FOOD=Pattern.compile(
        "米饭|炒菜|炒肉|馄饨|混沌|米线|鸡腿|面条|鸡蛋|牛奶|酸奶|土豆|面包|豆腐|蔬菜|青菜|排骨|饺子|水饺|盖饭|沙拉|火锅|羊肉|猪肉|牛肉|荤菜|素菜|便当|肉丸|豆花|红薯|粥");
    private WellnessChatMealContext() {}

    static Optional<Candidate> parse(List<AiStore.Message> history, LocalDate today) {
        return parse(history,today,"");
    }

    static Optional<Candidate> parse(List<AiStore.Message> history, LocalDate today,String request) {
        if(history==null || history.isEmpty())return Optional.empty();
        String requestedType=type(request==null?"":request);
        LocalDate requestedDate=explicitDate(request==null?"":request,today);
        // Select an authenticated user's described meal, never an assistant
        // response. An explicit meal request must not silently select lunch
        // when the user has asked to create a dinner card.
        for(int i=history.size()-1;i>=0;i--) {
            AiStore.Message source=history.get(i);
            if(!"user".equals(source.role()) || source.content()==null)continue;
            String text=source.content().strip();
            String type=type(text);
            if(type==null || (requestedType!=null && !requestedType.equals(type)))continue;
            if(!FOOD.matcher(text).find() && extractDescribedFood(text)==null){
                // The latest explicit meal description may be incomplete. Do
                // not replace it with an unrelated older meal.
                if(text.matches("(?s).*(?:吃了|吃的|吃过|喝了|点了|打算吃|准备吃|想吃|吃的是|餐[:：]|饭[:：]|餐吃|饭吃).*"))
                    return Optional.empty();
                continue;
            }
            // Resolve "今天/昨天" relative to the original user message,
            // not the follow-up after midnight or on a later day.
            LocalDate sourceDay=source.createdAt()==null?today:source.createdAt().toLocalDate();
            LocalDate date=mealDate(text,sourceDay);
            if(requestedDate!=null && !requestedDate.equals(date))
                continue; // Search older same-type meals for the explicitly requested date.
            if(date==null || date.isAfter(today.plusDays(1)) || date.isBefore(today.minusYears(2)))
                return Optional.empty();
            StringBuilder detail=new StringBuilder(text);
            // Short user clarifications (e.g. five people sharing two meat/two vegetable
            // dishes) belong to this meal; unrelated new meals do not.
            for(int j=i+1;j<history.size();j++){
                var follow=history.get(j);
                if(!"user".equals(follow.role()) || follow.content()==null)continue;
                String detailText=follow.content().strip();
                if(detailText.length()<=150 && (detailText.contains("两荤两素") ||
                    detailText.contains("饭多菜少") || detailText.contains("饭比较多") ||
                    detailText.contains("炒菜比较少")))detail.append("；").append(detailText);
            }
            BigDecimal kcal=WellnessAiDraftService.userProvidedCalories(text);
            // Repeated identical totals are common in pasted notes:
            // "晚餐（约650 kcal） ... 合计约650 kcal". A conflicting
            // combination (e.g. multiple dishes with different kcal) is not safe.
            if(kcal==null) kcal=repeatedIdenticalCalories(text);
            String sourceType="USER_ESTIMATE";
            if(kcal==null) {
                // Stop at the next independently described meal. A later lunch
                // estimate must never become the estimate for an earlier dinner.
                int until=history.size();
                for(int j=i+1;j<history.size();j++){
                    var next=history.get(j);
                    if(!"user".equals(next.role()) || next.content()==null)continue;
                    String other=next.content().strip();
                    if(type(other)!=null &&
                       (FOOD.matcher(other).find() || extractDescribedFood(other)!=null)) {
                        until=j;
                        break;
                    }
                }
                for(int j=until-1;j>i;j--){
                    var reply=history.get(j);
                    if(!"assistant".equals(reply.role()) || reply.content()==null)continue;
                    var m=ENERGY.matcher(reply.content());
                    if(m.find()){
                        try {
                            var energy=new BigDecimal(m.group(1));
                            if(energy.signum()>0 && energy.compareTo(new BigDecimal("20000"))<=0){
                                kcal=energy;
                                sourceType="AI_ESTIMATE";
                                break;
                            }
                        } catch(NumberFormatException ignored) { /* No guessed fallback */ }
                    }
                }
            }
            String name=foodName(detail.toString());
            if(name.isBlank())return Optional.empty();
            String note="根据本会话用户提供的餐食描述生成，实际分量请核对。"+
                ("AI_ESTIMATE".equals(sourceType)?"热量来自此前 AI 粗估，确认前不会入库。":"");
            if(detail.indexOf("两荤两素")>=0) note+="5人合点两荤两素。";
            if(detail.indexOf("饭比较多")>=0 || detail.indexOf("饭多菜少")>=0)
                note+="米饭偏多、炒菜偏少。";
            return Optional.of(new Candidate(date,type,name,kcal,sourceType,note,detail.toString()));
        }
        return Optional.empty();
    }

    /**
     * Preserve an explicitly enumerated ingredient list from the user's own message.
     * Never split an ambiguous composite dish such as "炒菜+米饭", never use
     * assistant text as ingredients, and never invent kcal for individual foods.
     */
    static List<ListedFood> listedFoods(String source) {
        if(source==null || source.isBlank())return List.of();
        String text=source.replace('\r','\n');
        int hotpot=text.indexOf("火锅");
        if(hotpot>=0) {
            text=text.substring(hotpot+"火锅".length());
            text=text.replaceFirst("^[的里：:、，,\\s]+","");
        } else {
            var prefix=Pattern.compile("吃了|吃的是|点了").matcher(text);
            if(!prefix.find())return List.of();
            text=text.substring(prefix.end());
        }
        text=text.split("[。！？]",2)[0];
        if(!text.matches("(?s).*[、，,；;\\n].*"))return List.of();
        List<ListedFood> result=new java.util.ArrayList<>();
        for(String segment:text.split("[、，,；;\\n]")) {
            String value=segment.strip().replaceFirst("^(?:[-*•]\\s*|\\d+[.、]\\s*)","");
            if(value.isBlank() || value.contains("没吃") || value.contains("不吃"))continue;
            value=value.replaceAll("[（(][^）)]*[）)]","");
            value=value.replaceFirst("^(?:还|又)?(?:吃了|点了|加了|还有|以及)\\s*","");
            value=value.strip();
            BigDecimal grams=BigDecimal.ZERO;
            var prefix=Pattern.compile("^(\\d+(?:\\.\\d+)?)\\s*(?:g|克)\\s*(.+)$",Pattern.CASE_INSENSITIVE).matcher(value);
            var suffix=Pattern.compile("^(.+?)\\s*(\\d+(?:\\.\\d+)?)\\s*(?:g|克)(?:\\s.*)?$",Pattern.CASE_INSENSITIVE).matcher(value);
            if(prefix.matches()) {
                grams=new BigDecimal(prefix.group(1));
                value=prefix.group(2).strip();
            } else if(suffix.matches()) {
                grams=new BigDecimal(suffix.group(2));
                value=suffix.group(1).strip();
            }
            value=value.replaceFirst("(?i)[:：]\\s*(?:约)?\\d+(?:\\.\\d+)?\\s*(?:kcal|千卡|大卡).*","");
            value=value.strip();
            if(value.isBlank() || value.matches("(?s).*(?:总计|总热量|合计|记录|帮我录入|帮我保存).*"))continue;
            if(value.length()>120)return List.of();
            result.add(new ListedFood(value,grams));
        }
        return result.size()>=2 ? List.copyOf(result) : List.of();
    }

    private static BigDecimal repeatedIdenticalCalories(String text) {
        var m=Pattern.compile("(?iu)(?<![\\d.])(\\d{1,4}(?:\\.\\d{1,2})?)\\s*(?:kcal|千卡|大卡|卡路里)(?!\\w)")
            .matcher(text);
        BigDecimal value=null;
        int count=0;
        while(m.find()) {
            if(++count>6)return null;
            BigDecimal next;
            try {next=new BigDecimal(m.group(1));}
            catch(NumberFormatException ex){return null;}
            if(next.signum()<=0 || next.compareTo(new BigDecimal("20000"))>0)return null;
            if(value!=null && value.compareTo(next)!=0)return null;
            value=next;
        }
        return count>=2?value:null;
    }

    private static LocalDate explicitDate(String text,LocalDate today) {
        if(text.isBlank())return null;
        // A user request's date constrains the history search; it never
        // silently rewrites the date of another historical meal.
        if(ISO.matcher(text).find() || CHINESE.matcher(text).find() ||
            text.contains("今天") || text.contains("昨天") ||
            text.contains("前天") || text.contains("昨晚") ||
            text.contains("明天") || text.contains("明日") ||
            text.contains("明晚") || text.contains("明早") ||
            text.contains("后天"))
            return mealDate(text,today);
        return null;
    }

    private static String extractDescribedFood(String text) {
        var m=Pattern.compile("(?:吃了|吃的|吃过|喝了|点了|打算吃|准备吃|想吃|吃的是)\\s*(.{1,75})")
            .matcher(text);
        if(!m.find())return null;
        String food=m.group(1).split("[，。！？；;\\n]|(?:帮我|给我|请你|记录|录入|保存)",2)[0].strip();
        // If the user has not yet named a food, do not fill from the assistant.
        return food.isEmpty() || food.length()>70 ? null : food;
    }

    private static String type(String text) {
        if(text.matches("(?s).*(?:晚餐|晚饭|晚上|今晚|明晚).*"))return "DINNER";
        if(text.matches("(?s).*(?:午餐|午饭|中午).*"))return "LUNCH";
        if(text.matches("(?s).*(?:早餐|早饭|早上).*"))return "BREAKFAST";
        if(text.contains("加餐") || text.contains("夜宵"))return "SNACK";
        return null;
    }
    private static LocalDate mealDate(String text,LocalDate today) {
        try {
            var iso=ISO.matcher(text);
            if(iso.find())return LocalDate.parse(iso.group(1));
            var cn=CHINESE.matcher(text);
            if(cn.find())return LocalDate.of(Integer.parseInt(cn.group(1)),
                Integer.parseInt(cn.group(2)),Integer.parseInt(cn.group(3)));
            if(text.contains("前天"))return today.minusDays(2);
            if(text.contains("昨天") || text.contains("昨晚"))return today.minusDays(1);
            if(text.contains("明天") || text.contains("明日") || text.contains("明晚") ||
                text.contains("明早"))return today.plusDays(1);
            if(text.contains("后天"))return null; // outside the supported date window
            return today;
        }catch(Exception ex){return null;}
    }
    private static String foodName(String original) {
        String food;
        if(original.contains("炒菜") && original.contains("米饭"))
            food="炒菜＋米饭";
        else if(original.contains("海味馄饨"))
            food="海味馄饨";
        else if(original.contains("馄饨") || original.contains("混沌"))
            food="馄饨";
        else if(original.contains("米饭") && original.contains("鸡腿"))
            food="鸡腿饭";
        else {
            var m=FOOD.matcher(original);
            if(m.find())food=m.group();
            else {
                String described=extractDescribedFood(original);
                if(described==null)return "";
                food=described;
            }
        }
        if(original.contains("两荤两素"))food+="（两荤两素）";
        if(original.contains("饭比较多") || original.contains("饭多菜少"))
            food+="（饭多菜少）";
        if(original.contains("大碗") && original.matches("(?s).*\\d+个.*"))
            food+="（大碗）";
        return food.length()>120?food.substring(0,120):food;
    }
}
