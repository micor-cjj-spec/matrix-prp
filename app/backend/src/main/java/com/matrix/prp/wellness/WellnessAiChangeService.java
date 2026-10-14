package com.matrix.prp.wellness;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.matrix.prp.ai.AiProviderClient;
import com.matrix.prp.ai.AiSettingsService;
import com.matrix.prp.ai.AiStore;
import com.matrix.prp.ai.DeepSeekClient;
import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.wellness.WellnessModels.*;
import java.math.BigDecimal;
import java.sql.Timestamp;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.YearMonth;
import java.time.ZoneOffset;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/** Human-targeted, one-time record changes. Model is never authorized to execute mutations. */
@Service
@Profile("!test")
public class WellnessAiChangeService {
    public record Request(String kind,long recordId,String operation,String instruction) {}
    public record Preview(String draftId,String action,String description,
        Map<String,Object> before,Map<String,Object> after,String expiresAt) {}
    public record Result(String action,String route,Object saved) {}
    private final JdbcTemplate db;
    private final WellnessService wellness;
    private final ObjectMapper json;
    private final AiSettingsService settings;
    private final AiProviderClient model;
    private final AiStore usage;
    private final int maxUserReq,maxGlobalReq;
    private final long maxUserTokens,maxGlobalTokens;

    public WellnessAiChangeService(JdbcTemplate db,WellnessService wellness,ObjectMapper json,
        AiSettingsService settings,AiProviderClient model,AiStore usage,
        @Value("${matrix-prp.ai.user-monthly-requests:200}") int maxUserReq, @Value("${matrix-prp.ai.global-monthly-requests:1000}") int maxGlobalReq,
        @Value("${matrix-prp.ai.user-monthly-reserved-tokens:250000}") long maxUserTokens,@Value("${matrix-prp.ai.global-monthly-reserved-tokens:1000000}") long maxGlobalTokens) {
        this.db=db;this.wellness=wellness;this.json=json;this.settings=settings;
        this.model=model;this.usage=usage;this.maxUserReq=maxUserReq;
        this.maxGlobalReq=maxGlobalReq;this.maxUserTokens=maxUserTokens;
        this.maxGlobalTokens=maxGlobalTokens;
    }
    static ResponseStatusException invalid(String reason) {
        return new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY,reason);
    }
    static String table(String kind) {
        return switch(kind){
            case "meal" -> "prp_wellness_meals";
            case "exercise" -> "prp_wellness_exercises";
            case "metric" -> "prp_wellness_body_metrics";
            default -> throw invalid("Unsupported record type");
        };
    }
    static String action(String kind,String op) {
        table(kind);
        if(!Set.of("update","delete").contains(op))throw invalid("Unsupported action");
        return kind+"."+op;
    }
    private static Map<String,Object> map(Object...pairs){
        Map<String,Object> out=new LinkedHashMap<>();
        for(int i=0;i<pairs.length;i+=2)out.put((String)pairs[i],pairs[i+1]);
        return out;
    }
    public Map<String,Object> current(String kind,long id){
        if(id<=0)throw invalid("Invalid record ID");
        return switch(kind){
            case "meal" -> {
                Meal v=wellness.ownedMeal(id);
                yield map("date",v.mealDate().toString(),"mealType",v.mealType(),
                    "note",v.note(),"items",v.items().stream().map(i->
                        map("foodId",i.foodId(),"name",i.foodName(),"grams",i.grams(),
                            "calories",i.foodId()<=0?i.calories():null)).toList());
            }
            case "exercise" -> {
                Exercise v=wellness.ownedExercise(id);
                yield map("date",v.performedOn().toString(),"name",v.name(),
                    "durationMinutes",v.durationMinutes(),"estimatedKcal",v.estimatedKcal(),
                    "note",v.note());
            }
            case "metric" -> {
                BodyMetric v=wellness.ownedMetric(id);
                yield map("date",v.measuredOn().toString(),"weightKg",v.weightKg(),
                    "bodyFatPct",v.bodyFatPct(),"waistCm",v.waistCm());
            }
            default -> throw invalid("Unknown record type");
        };
    }
    private static LocalDate date(JsonNode node){
        if(!node.isTextual())throw invalid("Date required");
        try{return LocalDate.parse(node.asText());}
        catch(Exception ex){throw invalid("Invalid date");}
    }
    private static String word(JsonNode node,int max,boolean optional){
        if((node.isNull()||node.isMissingNode())&&optional)return "";
        if(!node.isTextual()||node.asText().length()>max||
            (!optional&&node.asText().isBlank()))throw invalid("Invalid text field");
        return node.asText().trim();
    }
    private static BigDecimal number(JsonNode node,String label,String min,String max,boolean nullable){
        if((node.isNull()||node.isMissingNode())&&nullable)return null;
        if(!node.isNumber())throw invalid("Invalid "+label);
        BigDecimal n=node.decimalValue();
        if(n.compareTo(new BigDecimal(min))<0||n.compareTo(new BigDecimal(max))>0)
            throw invalid("Invalid "+label+" range");
        return n;
    }
    Map<String,Object> validate(String kind,JsonNode node){
        if(!node.isObject()||node.toString().length()>5000)throw invalid("Invalid change payload");
        LocalDate d=date(node.path("date"));
        if(d.isAfter(LocalDate.now().plusDays(1))||d.isBefore(LocalDate.now().minusYears(2)))
            throw invalid("Date outside allowed range");
        return switch(kind){
            case "meal" -> {
                String type=word(node.path("mealType"),16,false);
                if(!Set.of("BREAKFAST","LUNCH","DINNER","SNACK").contains(type))
                    throw invalid("Unsupported meal type");
                JsonNode items=node.path("items");
                if(!items.isArray()||items.isEmpty()||items.size()>50)
                    throw invalid("Food list missing or too long");
                List<Map<String,Object>> safe=new ArrayList<>();
                for(JsonNode item:items) {
                    if(!item.path("foodId").canConvertToLong())
                        throw invalid("Food ID required");
                    long foodId=item.path("foodId").asLong();
                    if(foodId>0) {
                        Food food=wellness.accessibleFood(foodId);
                        safe.add(map("foodId",food.id(),"name",food.name(),
                            "grams",number(item.path("grams"),"grams","0.1","10000",false),
                            "calories",null));
                    } else {
                        String name=word(item.path("name"),120,false);
                        BigDecimal kcal=number(item.path("calories"),"custom calories","0.01","20000",false);
                        if(kcal.scale()>2)throw invalid("Custom calories precision");
                        safe.add(map("foodId",0,"name",name,
                            "grams",number(item.path("grams"),"grams","0","3000",false),
                            "calories",kcal));
                    }
                }
                yield map("date",d.toString(),"mealType",type,
                    "note",word(node.path("note"),500,true),"items",safe);
            }
            case "exercise" -> {
                JsonNode minutes=node.path("durationMinutes");
                if(!minutes.isIntegralNumber()||minutes.asInt()<1||minutes.asInt()>1440)
                    throw invalid("Invalid exercise duration");
                yield map("date",d.toString(),"name",word(node.path("name"),100,false),
                    "durationMinutes",minutes.asInt(),
                    "estimatedKcal",number(node.path("estimatedKcal"),"kcal","0","20000",true),
                    "note",word(node.path("note"),500,true));
            }
            case "metric" -> map("date",d.toString(),
                "weightKg",number(node.path("weightKg"),"weightKg","0.1","500",false),
                "bodyFatPct",number(node.path("bodyFatPct"),"bodyFatPct","0","100",true),
                "waistCm",number(node.path("waistCm"),"waistCm","0","300",true));
            default -> throw invalid("Unknown record type");
        };
    }
    private JsonNode modelPatch(String kind,Map<String,Object> original,String instruction){
        long user=CurrentUser.id();
        var runtime=settings.resolve(user);
        String month=YearMonth.now(ZoneOffset.UTC).toString();
        usage.reserve(user,month,3000,maxUserReq,maxUserTokens,maxGlobalReq,maxGlobalTokens);
        String system="你是健康记录修改 JSON 解析器。只输出JSON对象，仅包含用户明确要求修改的字段，不要输出Markdown。"+
            "允许字段：meal为date,mealType,note,items；exercise为date,name,durationMinutes,estimatedKcal,note；"+
            "metric为date,weightKg,bodyFatPct,waistCm。meal.items如修改，必须输出完整原有列表，"+
            "保持每个原foodId不变，仅修改grams。禁止添加/删除条目、用户ID、记录ID，数据不确定则输出{}。";
        try{
            var answer=model.stream(runtime,List.of(
                new DeepSeekClient.ChatMessage("system",system),
                new DeepSeekClient.ChatMessage("user","记录类型："+kind+"；原记录："+json.writeValueAsString(original)+
                    "；请按要求修改："+instruction)),700,x->{});
            usage.completed(user,month,answer.inputTokens(),answer.outputTokens());
            String s=answer.answer();
            int left=s.indexOf('{'),right=s.lastIndexOf('}');
            if(s.length()>4000||left<0||right<left)throw invalid("AI returned invalid draft");
            JsonNode patch=json.readTree(s.substring(left,right+1));
            if(!patch.isObject())throw invalid("AI edits must be a JSON object");
            return patch;
        }catch(ResponseStatusException e){throw e;}
          catch(Exception e){throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,
              "AI modification failed; use manual correction");}
    }
    private JsonNode merge(String kind,JsonNode original,JsonNode patch){
        if(!patch.isObject())throw invalid("Invalid patch");
        Set<String> allowed=switch(kind){
            case "meal" -> Set.of("date","mealType","note","items");
            case "exercise" -> Set.of("date","name","durationMinutes","estimatedKcal","note");
            case "metric" -> Set.of("date","weightKg","bodyFatPct","waistCm");
            default -> throw invalid("Unsupported record type");
        };
        ObjectNode target=(ObjectNode)original.deepCopy();
        var fields=patch.fields();
        while(fields.hasNext()){
            var item=fields.next();
            if(!allowed.contains(item.getKey()))throw invalid("Unexpected AI field");
            if(kind.equals("meal")&&item.getKey().equals("items")){
                JsonNode old=original.path("items"),next=item.getValue();
                if(!next.isArray()||next.size()!=old.size())
                    throw invalid("AI may only adjust existing food weights");
                for(int i=0;i<next.size();i++) {
                    if(next.get(i).path("foodId").asLong(-1)!=old.get(i).path("foodId").asLong(-2))
                        throw invalid("AI cannot switch foods");
                    if(old.get(i).path("foodId").asLong(0)<=0 &&
                       (!next.get(i).path("name").asText().equals(old.get(i).path("name").asText()) ||
                        !next.get(i).path("calories").equals(old.get(i).path("calories"))))
                        throw invalid("AI cannot rewrite custom calorie snapshots");
                }
            }
            target.set(item.getKey(),item.getValue());
        }
        return target;
    }
    public Preview prepare(Request input){
        if(input==null)throw invalid("Record selection required");
        String action=action(input.kind(),input.operation());
        String instruction=input.instruction()==null?"":input.instruction().trim();
        if(instruction.length()>500)throw invalid("Instruction too long");
        Map<String,Object> before=current(input.kind(),input.recordId());
        JsonNode proposed=json.valueToTree(before);
        String source="user-reviewed";
        if(input.operation().equals("update")&&!instruction.isEmpty()){
            proposed=merge(input.kind(),proposed,modelPatch(input.kind(),before,instruction));
            var selected=settings.selection(CurrentUser.id());
            source=selected.provider()+"/"+selected.model();
        }
        // Deletes only require ownership and an exact snapshot, not a valid current food
        // reference. Legacy meal data can be removed without repairing its ingredients.
        Map<String,Object> after=input.operation().equals("delete")
            ? before : validate(input.kind(),proposed);
        Map<String,Object> payload=map("kind",input.kind(),"recordId",input.recordId(),
            "operation",input.operation(),"before",before,"after",after);
        String draftId=UUID.randomUUID().toString();
        LocalDateTime expires=LocalDateTime.now().plusMinutes(15);
        try{
            db.update("INSERT INTO prp_wellness_ai_drafts "+
                "(id,user_id,action_type,payload_json,description,model_used,expires_at) VALUES (?,?,?,?,?,?,?)",
                draftId,CurrentUser.id(),action,json.writeValueAsString(payload),
                "核对 "+action+" #"+input.recordId(),source,Timestamp.valueOf(expires));
        }catch(Exception ex){throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
            "Cannot persist change draft");}
        return new Preview(draftId,action,"核对 "+action+" #"+input.recordId(),
            before,after,expires.toString());
    }
    private static void validDraftId(String id){
        try{UUID.fromString(id);}
        catch(Exception ex){throw invalid("Invalid draft ID");}
    }
    private Map<String,Object> lockedDraft(String id){
        validDraftId(id);
        var rows=db.queryForList("SELECT action_type,payload_json,status,expires_at "+
            "FROM prp_wellness_ai_drafts WHERE id=? AND user_id=? FOR UPDATE",id,CurrentUser.id());
        if(rows.isEmpty())throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Draft not found");
        var row=rows.getFirst();
        if(!"PENDING".equals(row.get("status"))||
            !((Timestamp)row.get("expires_at")).toLocalDateTime().isAfter(LocalDateTime.now()))
            throw new ResponseStatusException(HttpStatus.CONFLICT,"Draft expired or used");
        return row;
    }
    @Transactional
    public Preview edit(String id,JsonNode updated){
        var row=lockedDraft(id);
        String action=String.valueOf(row.get("action_type"));
        if(!action.endsWith(".update"))throw invalid("Delete draft cannot be changed");
        try{
            ObjectNode payload=(ObjectNode)json.readTree(String.valueOf(row.get("payload_json")));
            String kind=payload.path("kind").asText();
            Map<String,Object> after=validate(kind,updated);
            payload.set("after",json.valueToTree(after));
            if(db.update("UPDATE prp_wellness_ai_drafts SET payload_json=? "+
                "WHERE id=? AND user_id=? AND status='PENDING'",
                json.writeValueAsString(payload),id,CurrentUser.id())!=1)
                throw invalid("Draft no longer editable");
            return new Preview(id,action,"核对 "+action,
                json.convertValue(payload.path("before"),Map.class),after,
                ((Timestamp)row.get("expires_at")).toLocalDateTime().toString());
        }catch(ResponseStatusException e){throw e;}
          catch(Exception e){throw invalid("Invalid modification fields");}
    }
    private void lockTarget(String kind,long id) {
        if(db.queryForList("SELECT id FROM "+table(kind)+" WHERE id=? AND user_id=? FOR UPDATE",
            id,CurrentUser.id()).isEmpty())
            throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Record no longer exists");
    }
    @Transactional
    public Result confirm(String id){
        var row=lockedDraft(id);
        try{
            JsonNode payload=json.readTree(String.valueOf(row.get("payload_json")));
            String kind=payload.path("kind").asText(),op=payload.path("operation").asText();
            if(!action(kind,op).equals(row.get("action_type")))
                throw invalid("Draft action was tampered");
            long target=payload.path("recordId").asLong();
            lockTarget(kind,target);
            if(!json.valueToTree(current(kind,target)).equals(payload.path("before")))
                throw new ResponseStatusException(HttpStatus.CONFLICT,
                    "The record has changed; open a fresh preview");
            Object saved=null;
            if(op.equals("delete")){
                switch(kind){
                    case "meal" -> wellness.deleteMeal(target);
                    case "exercise" -> wellness.deleteExercise(target);
                    case "metric" -> wellness.deleteMetric(target);
                    default -> throw invalid("Unsupported delete target");
                }
            }else{
                JsonNode after=payload.path("after");
                validate(kind,after);
                LocalDate day=date(after.path("date"));
                saved=switch(kind){
                    case "meal" -> {
                        List<ItemInput> items=new ArrayList<>();
                        List<WellnessService.AiMealItem> mixed=new ArrayList<>();
                        boolean hasCustom=false;
                        JsonNode beforeItems=payload.path("before").path("items");
                        for(int i=0;i<after.path("items").size();i++) {
                            JsonNode item=after.path("items").get(i);
                            long foodId=item.path("foodId").asLong(0);
                            BigDecimal grams=item.path("grams").decimalValue();
                            if(foodId>0) {
                                items.add(new ItemInput(foodId,grams));
                                mixed.add(new WellnessService.AiMealItem(foodId,null,grams,null));
                            } else {
                                JsonNode original=beforeItems.get(i);
                                if(original==null ||
                                   !item.path("name").equals(original.path("name")) ||
                                   !item.path("calories").equals(original.path("calories")))
                                    throw invalid("Cannot change historical calorie snapshot through AI edit");
                                hasCustom=true;
                                mixed.add(new WellnessService.AiMealItem(null,item.path("name").asText(),
                                    grams,item.path("calories").decimalValue()));
                            }
                        }
                        if(hasCustom) yield wellness.updateAiMeal(target,day,after.path("mealType").asText(),
                            after.path("note").asText(""),mixed);
                        yield wellness.updateMeal(target,new MealInput(day,after.path("mealType").asText(),
                            after.path("note").asText(""),items,null));
                    }
                    case "exercise" -> wellness.updateExercise(target,new ExerciseInput(day,
                        after.path("name").asText(),after.path("durationMinutes").asInt(),
                        after.path("estimatedKcal").isNull()?null:after.path("estimatedKcal").decimalValue(),
                        after.path("note").asText("")));
                    case "metric" -> wellness.updateMetric(target,new BodyMetricInput(day,
                        after.path("weightKg").decimalValue(),
                        after.path("bodyFatPct").isNull()?null:after.path("bodyFatPct").decimalValue(),
                        after.path("waistCm").isNull()?null:after.path("waistCm").decimalValue()));
                    default -> throw invalid("Unsupported update target");
                };
            }
            if(db.update("UPDATE prp_wellness_ai_drafts SET status='CONSUMED',consumed_at=NOW() "+
                "WHERE id=? AND user_id=? AND status='PENDING'",id,CurrentUser.id())!=1)
                throw new ResponseStatusException(HttpStatus.CONFLICT,"Draft already used");
            return new Result(kind+"."+op,"/wellness?date="+payload.path("before").path("date").asText(),saved);
        }catch(ResponseStatusException e){throw e;}
          catch(Exception e){throw invalid("Change rejected; no data committed");}
    }
}
