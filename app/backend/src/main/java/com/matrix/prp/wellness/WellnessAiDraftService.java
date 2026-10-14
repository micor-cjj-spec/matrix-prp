package com.matrix.prp.wellness;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.ai.AiProviderCatalog;
import com.matrix.prp.ai.AiSettingsService;
import com.matrix.prp.ai.AiStore;
import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.wellness.WellnessModels.*;
import java.math.BigDecimal;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.YearMonth;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

/**
 * AI proposes, server validates, human confirms. The model cannot mutate business state,
 * choose the user, execute SQL, or construct outbound URLs.
 */
@Service
@org.springframework.context.annotation.Profile("!test")
public class WellnessAiDraftService {
    public record Preview(String draftId, String action, String description,
                          String modelUsed, Map<String,Object> values, String expiresAt) {}
    public record Outcome(String action, Object saved, String route) {}
    public record DraftView(Preview draft,String status) {}
    private final JdbcTemplate db;
    private final WellnessService wellness;
    private final AiSettingsService settings;
    private final AiStore usage;
    private final ObjectMapper json;
    private final int userRequests, globalRequests;
    private final long userTokens, globalTokens;
    private final HttpClient http=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(6))
        .followRedirects(HttpClient.Redirect.NEVER).build();

    public WellnessAiDraftService(JdbcTemplate db, WellnessService wellness, AiSettingsService settings,
        AiStore usage, ObjectMapper json,
        @Value("${matrix-prp.ai.user-monthly-requests:200}") int userRequests,
        @Value("${matrix-prp.ai.global-monthly-requests:1000}") int globalRequests,
        @Value("${matrix-prp.ai.user-monthly-reserved-tokens:250000}") long userTokens,
        @Value("${matrix-prp.ai.global-monthly-reserved-tokens:1000000}") long globalTokens) {
        this.db=db; this.wellness=wellness; this.settings=settings; this.usage=usage; this.json=json;
        this.userRequests=userRequests;this.globalRequests=globalRequests;
        this.userTokens=userTokens;this.globalTokens=globalTokens;
    }
    private LocalDate today(){return LocalDate.now(ZoneId.of(wellness.profile().timezone()));}

    /**
     * Bounded repeat of an actually saved owner-owned meal, not a second AI guess.
     * Returns null when the request is not an explicit, supported historical meal copy.
     */
    public Preview prepareRepeat(String input) {
        var intent=WellnessMealRepeatIntent.parse(input,today());
        if(intent.isEmpty()) return null;
        var request=intent.get();
        var candidates=wellness.recentMeals(request.mealType(),today(),31).stream()
            .filter(meal->!request.targets().contains(meal.mealDate())).toList();
        if(candidates.isEmpty())
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY,
                "没有找到已保存的同类餐次，请先保存一条来源记录，并明确写明食物及份量");
        var source=candidates.getFirst();
        if(candidates.stream().filter(meal->meal.mealDate().equals(source.mealDate())).count()>1)
            throw new ResponseStatusException(HttpStatus.CONFLICT,
                "来源日期有多条同类餐次，请明确选择要复制的那一条");
        if(source.items().isEmpty() || source.items().size()>8 ||
            source.items().stream().anyMatch(item->item.grams()==null ||
                item.grams().signum()<0 || item.grams().compareTo(BigDecimal.valueOf(3000))>0 ||
                (item.foodId()>0 && item.grams().signum()==0) ||
                (item.foodId()<=0 && (item.foodName()==null || item.foodName().isBlank() ||
                    item.calories()==null || item.calories().signum()<=0 ||
                    item.calories().compareTo(new BigDecimal("20000"))>0))))
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY,
                "来源餐次包含无法安全复制的食物，请先核对健康中心的来源记录");
        for(var item:source.items()) if(item.foodId()>0) wellness.accessibleFood(item.foodId());
        for(var target:request.targets())
            if(wellness.meals(target).stream().anyMatch(m->m.mealType().equals(request.mealType())))
                throw new ResponseStatusException(HttpStatus.CONFLICT,
                    target+" 已有同类型餐次，请先检查健康中心，避免重复记录");
        List<Map<String,Object>> foods=new ArrayList<>();
        for(var item:source.items()) {
            Map<String,Object> copy=new LinkedHashMap<>();
            copy.put("foodId",item.foodId());
            copy.put("name",item.foodName());
            copy.put("grams",item.grams());
            copy.put("calories",item.calories());
            copy.put("mode",item.foodId()>0?"catalog":"manual");
            if(item.foodId()<=0) copy.put("manualCalories",item.calories());
            foods.add(copy);
        }
        Map<String,Object> values=new LinkedHashMap<>();
        values.put("date",request.targets().getFirst().toString());
        values.put("sourceMealId",source.id());
        values.put("sourceDate",source.mealDate().toString());
        values.put("mealType",request.mealType());
        values.put("targets",request.targets().stream().map(LocalDate::toString).toList());
        values.put("items",foods);
        values.put("note",source.note()==null?"":source.note());
        String id=UUID.randomUUID().toString();
        LocalDateTime expiry=LocalDateTime.now().plusMinutes(15);
        String desc="将 "+source.mealDate()+" 已保存的"+request.mealType()+"复制到 "+
            request.targets().size()+" 个日期，确认后批量保存";
        try {
            db.update("INSERT INTO prp_wellness_ai_drafts " +
                "(id,user_id,action_type,payload_json,description,model_used,expires_at) VALUES (?,?,?,?,?,?,?)",
                id,CurrentUser.id(),"meal.copy_batch",json.writeValueAsString(values),desc,
                "system/saved-meal",java.sql.Timestamp.valueOf(expiry));
        } catch(com.fasterxml.jackson.core.JsonProcessingException e) {
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR,"无法编码批量饮食草稿");
        }
        return new Preview(id,"meal.copy_batch",desc,"system/saved-meal",values,expiry.toString());
    }

    /**
     * Structured multi-meal input is backed only by energy amounts actually typed
     * by the user, never by model-authored nutritional claims.
     */
    public Preview prepareBatch(String input) {
        WellnessMealBatchIntent.Batch request;
        try {
            var parsed=WellnessMealBatchIntent.parse(input,today());
            if(parsed.isEmpty())return null;
            request=parsed.get();
        }catch(IllegalArgumentException e){
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY,e.getMessage());
        }
        long user=CurrentUser.id();
        List<String> existing=wellness.meals(request.date()).stream()
            .map(Meal::mealType).distinct().toList();
        List<Map<String,Object>> meals=new ArrayList<>();
        for(var meal:request.meals()){
            if(existing.contains(meal.type()))continue;
            List<Map<String,Object>> items=new ArrayList<>();
            for(var food:meal.foods()){
                Map<String,Object> item=new LinkedHashMap<>();
                item.put("foodId",0);
                item.put("name",food.name());
                item.put("grams",food.grams());
                item.put("mode","manual");
                item.put("manualCalories",food.calories());
                item.put("calories",food.calories());
                items.add(item);
            }
            Map<String,Object> record=new LinkedHashMap<>();
            record.put("mealType",meal.type());
            record.put("items",items);
            record.put("note","用户明确提供的单次估算热量，宏量营养素未知");
            record.put("totalCalories",meal.declaredTotal());
            meals.add(record);
        }
        if(meals.isEmpty())throw new ResponseStatusException(HttpStatus.CONFLICT,
            "当天这些餐次已有记录，请先核对健康中心，不能重复录入");
        Map<String,Object> payload=new LinkedHashMap<>();
        payload.put("date",request.date().toString());
        payload.put("meals",meals);
        payload.put("alreadyExistingTypes",existing.stream()
            .filter(t->request.meals().stream().anyMatch(m->m.type().equals(t))).toList());
        String id=UUID.randomUUID().toString();
        LocalDateTime expires=LocalDateTime.now().plusMinutes(15);
        String desc=request.date()+" 共 "+meals.size()+" 餐待确认（已存在的餐次不重复写入）";
        db.update("INSERT INTO prp_wellness_ai_drafts " +
            "(id,user_id,action_type,payload_json,description,model_used,expires_at) VALUES (?,?,?,?,?,?,?)",
            id,user,"meal.create_batch",serialize(payload),desc,"system/user-supplied-kcal",
            java.sql.Timestamp.valueOf(expires));
        return new Preview(id,"meal.create_batch",desc,"system/user-supplied-kcal",payload,expires.toString());
    }

    private String serialize(Object payload){
        try{return json.writeValueAsString(payload);}
        catch(com.fasterxml.jackson.core.JsonProcessingException e){
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Invalid meal data");
        }
    }

    public Preview prepare(String input, MultipartFile image) {
        long user=CurrentUser.id();
        if(input==null || input.isBlank() || input.length()>1500)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Describe the record in 1-1500 characters");
        byte[] bytes=null;
        String mime=null;
        if(image!=null && !image.isEmpty()){
            if(image.getSize()>3_000_000)
                throw new ResponseStatusException(HttpStatus.PAYLOAD_TOO_LARGE,"Image must be <=3MB");
            try { bytes=image.getBytes(); }
            catch(Exception e){throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Cannot read image");}
            mime=detect(bytes);
            if(mime==null) throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Supported: JPEG, PNG, WebP");
        }
        var config=settings.resolve(user);
        String model=config.model();
        if(bytes!=null){
            // Chat Completions vision requires a vision-capable model, not deepseek-chat.
            if(config.provider().id().equals("deepseek")) model="deepseek-flash";
            else if(config.provider().id().equals("openai") &&
                Set.of("gpt-4.1-mini","gpt-4.1").contains(model)) { /* selected model supports images */ }
            else if((config.provider().id().equals("kimi")||config.provider().id().equals("kimi-global")) &&
                model.equals("kimi-k2.5")) { /* supported */ }
            else throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                "Selected model cannot accept pictures. Choose DeepSeek, OpenAI GPT-4.1 or Kimi K2.5.");
        }
        String month=YearMonth.now(ZoneOffset.UTC).toString();
        long reserved=bytes==null?2200:4800;
        usage.reserve(user,month,reserved,userRequests,userTokens,globalRequests,globalTokens);
        JsonNode root=request(config,model,input,bytes,mime);
        JsonNode output=parseJson(root.path("choices").path(0).path("message").path("content").asText(""));
        Map<String,Object> verified=verify(output);
        String action=output.path("action").asText();
        // Explicit calories originate only in the authenticated user's message, never the model JSON.
        if("meal.create".equals(action)) applyUserCalorieEstimate(verified,input);
        String description=description(action,verified);
        String id=UUID.randomUUID().toString();
        LocalDateTime expiry=LocalDateTime.now().plusMinutes(15);
        try {
            db.update("INSERT INTO prp_wellness_ai_drafts " +
                "(id,user_id,action_type,payload_json,description,model_used,expires_at) VALUES (?,?,?,?,?,?,?)",
                id,user,action,json.writeValueAsString(verified),description,
                config.provider().id()+"/"+model,java.sql.Timestamp.valueOf(expiry));
        }catch(Exception e){throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,"Cannot save draft");}
        long inputTokens=root.path("usage").path("prompt_tokens").asLong(0);
        long outputTokens=root.path("usage").path("completion_tokens").asLong(0);
        usage.completed(user,month,inputTokens,outputTokens);
        return new Preview(id,action,description,config.provider().id()+"/"+model,verified,expiry.toString());
    }

    /** Owner-scoped reload for persisted chat confirmation cards; never exposes other users' drafts. */
    public DraftView getDraft(String draftId) {
        long user=CurrentUser.id();
        if(draftId==null || !draftId.matches("[0-9a-fA-F-]{36}"))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Invalid draft");
        List<Map<String,Object>> rows=db.queryForList(
            "SELECT action_type,payload_json,description,model_used,status,expires_at FROM prp_wellness_ai_drafts " +
            "WHERE id=? AND user_id=?",draftId,user);
        if(rows.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Draft not found");
        var row=rows.get(0);
        var expires=((java.sql.Timestamp)row.get("expires_at")).toLocalDateTime();
        String status=String.valueOf(row.get("status"));
        if("PENDING".equals(status) && !expires.isAfter(LocalDateTime.now())) status="EXPIRED";
        try {
            @SuppressWarnings("unchecked")
            Map<String,Object> values=json.readValue(String.valueOf(row.get("payload_json")),Map.class);
            return new DraftView(new Preview(draftId,String.valueOf(row.get("action_type")),
                String.valueOf(row.get("description")),String.valueOf(row.get("model_used")),
                values,expires.toString()),status);
        } catch(com.fasterxml.jackson.core.JsonProcessingException e) {
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR,"Invalid stored health draft");
        }
    }

    static String detect(byte[] b){
        if(b==null || b.length<12)return null;
        if((b[0]&255)==255 && (b[1]&255)==216 && (b[2]&255)==255)return "image/jpeg";
        if((b[0]&255)==137 && b[1]==80 && b[2]==78 && b[3]==71)return "image/png";
        if(b[0]==82 && b[1]==73 && b[2]==70 && b[3]==70 &&
            b[8]==87 && b[9]==69 && b[10]==66 && b[11]==80)return "image/webp";
        return null;
    }
    private JsonNode request(AiSettingsService.Runtime config,String model,String prompt,byte[] image,String mime){
        try{
            Map<String,Object> payload=new LinkedHashMap<>();
            payload.put("model",model);payload.put("stream",false);payload.put("max_tokens",700);
            String rules="你是PRP健康数据录入解析器。只输出一个JSON对象，没有Markdown。"+
                "只能创建三种记录: meal.create、exercise.create、metric.create。"+
                "JSON meal.create: {action, date:yyyy-MM-dd, mealType:BREAKFAST/LUNCH/DINNER/SNACK, "+
                "items:[{name:食物中文名称,grams:克数}],note:备注}；"+
                "exercise.create: {action,date,name,durationMinutes,estimatedKcal,note}；"+
                "metric.create: {action,date,weightKg,bodyFatPct,waistCm}。"+
                "若日期未指定用"+today()+"。餐次类型按时间与语义判断；文字只有数量时，只有常见明确份量可保守换算：鸡蛋可食部约50g/个、全麦面包约30g/片、牛奶约1g/ml；请在note明确写估算及份量，其他未知克重输出0不可伪造；照片可粗略估量分量（克）但务必提示用户核对，"+
                "图片无法精确估计油量或分量，请提醒用户核对；每个图片不超过8种食物。"+
                "仅根据用户提供的信息填写，不能读取历史数据，也不得执行修改或删除。";
            if(config.provider().anthropic()){
                if(image!=null) throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Vision not available for this provider");
                payload.put("system",rules);payload.put("max_tokens",700);
                payload.put("messages",List.of(Map.of("role","user","content",prompt)));
                payload.remove("stream");
            } else {
                Object content=image==null?prompt:List.of(
                    Map.of("type","text","text",prompt),
                    Map.of("type","image_url","image_url",Map.of("url",
                        "data:"+mime+";base64,"+Base64.getEncoder().encodeToString(image))));
                payload.put("messages",List.of(Map.of("role","system","content",rules),
                    Map.of("role","user","content",content)));
            }
            HttpRequest.Builder request=HttpRequest.newBuilder(config.provider().endpoint())
                .timeout(Duration.ofSeconds(45)).header("Content-Type","application/json")
                .POST(HttpRequest.BodyPublishers.ofByteArray(json.writeValueAsBytes(payload)));
            if(config.provider().anthropic())
                request.header("x-api-key",config.apiKey()).header("anthropic-version","2023-06-01");
            else request.header("Authorization","Bearer "+config.apiKey());
            HttpResponse<String> response=http.send(request.build(),HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            if(response.statusCode()!=200)
                throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,
                    "Vision/text model rejected request ("+response.statusCode()+")");
            if(response.body().length()>60_000)throw new IllegalArgumentException("Model response too large");
            JsonNode result=json.readTree(response.body());
            if(config.provider().anthropic()){
                StringBuilder text=new StringBuilder();
                for(JsonNode block:result.path("content")) if(block.path("type").asText().equals("text"))
                    text.append(block.path("text").asText());
                return json.createObjectNode().set("choices",
                    json.createArrayNode().add(json.createObjectNode().set("message",
                        json.createObjectNode().put("content",text.toString()))));
            }
            return result;
        }catch(ResponseStatusException ex){throw ex;}
         catch(Exception ex){throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,"AI record parsing failed");}
    }
    private JsonNode parseJson(String s){
        if(s.length()>6000) throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY,"AI draft too large");
        int start=s.indexOf('{'),end=s.lastIndexOf('}');
        if(start<0||end<=start) throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY,
            "AI did not return a valid record; use the manual form");
        try{return json.readTree(s.substring(start,end+1));}
        catch(Exception e){throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY,
            "AI did not return valid JSON; use the manual form");}
    }
    private static String date(JsonNode node){
        if(!node.path("date").isTextual()) throw invalid("Date required");
        try {return LocalDate.parse(node.path("date").asText()).toString();}
        catch(Exception e){throw invalid("Invalid date");}
    }
    private static BigDecimal decimal(JsonNode node,String key,boolean required){
        if(!node.hasNonNull(key) && !required)return null;
        JsonNode v=node.path(key);
        if(!v.isNumber()) throw invalid("Invalid "+key);
        BigDecimal d=v.decimalValue();
        if(d.signum()<0)throw invalid("Negative "+key);
        return d;
    }
    private static ResponseStatusException invalid(String message){
        return new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY,message+
            " — please correct the description or enter it manually");
    }
    /** Extract at most one explicitly user-typed energy amount for a single food. */
    static BigDecimal userProvidedCalories(String input) {
        if(input==null) return null;
        var matcher=java.util.regex.Pattern.compile(
            "(?iu)(?<![\\d.])(\\d+(?:\\.\\d{1,2})?)\\s*(?:千卡|大卡|kcal|卡路里)(?!\\w)").matcher(input);
        BigDecimal found=null;
        while(matcher.find()){
            if(found!=null)return null; // ambiguous multi-food or multiple energy amounts
            try { found=new BigDecimal(matcher.group(1)); }
            catch(NumberFormatException e){ return null; }
        }
        return found!=null && found.signum()>0 &&
            found.compareTo(new BigDecimal("20000"))<=0 ? found : null;
    }
    @SuppressWarnings("unchecked")
    static void applyUserCalorieEstimate(Map<String,Object> values,String source) {
        BigDecimal energy=userProvidedCalories(source);
        if(energy==null) return;
        var rows=(List<Map<String,Object>>)values.get("items");
        if(rows==null || rows.size()!=1) return;
        Map<String,Object> item=rows.getFirst();
        item.put("foodId",0L);
        item.put("mode","manual");
        item.put("manualCalories",energy);
        // Optional user-spoken merchant/serving qualifiers are hints, not verified vendor facts.
        if(source.contains("沙县小吃")) item.put("merchantName","沙县小吃");
        if(source.contains("大碗")) item.put("portionLabel","大碗");
        else if(source.contains("小碗")) item.put("portionLabel","小碗");
        var count=java.util.regex.Pattern.compile("(\\d{1,4})\\s*个").matcher(source);
        if(count.find()) item.put("portionCount",Integer.parseInt(count.group(1)));
        if(source.contains("ChatGPT") || source.contains("GPT") || source.contains("AI估算") ||
           source.contains("AI 估算")) item.put("sourceType","AI_ESTIMATE");
        item.put("calories",energy);
    }
    Map<String,Object> verify(JsonNode node){ return verify(node,false); }
    Map<String,Object> verify(JsonNode node,boolean edited){
        if(!node.isObject())throw invalid("Invalid AI action");
        String action=node.path("action").asText("");
        String day=date(node);
        LocalDate when=LocalDate.parse(day);
        if(when.isAfter(today().plusDays(1)) || when.isBefore(today().minusYears(2)))
            throw invalid("Date outside recording range");
        Map<String,Object> m=new LinkedHashMap<>();m.put("date",day);
        switch(action){
            case "meal.create" -> {
                String type=node.path("mealType").asText("");
                if(!Set.of("BREAKFAST","LUNCH","DINNER","SNACK").contains(type))throw invalid("Unknown meal type");
                JsonNode items=node.path("items");
                if(!items.isArray()||items.isEmpty()||items.size()>8) throw invalid("Food items missing");
                List<Map<String,Object>> parsed=new ArrayList<>();
                for(JsonNode item:items){
                    String name=item.path("name").asText("").trim();
                    if(name.isBlank()||name.length()>120)throw invalid("Food name missing");
                    BigDecimal grams=decimal(item,"grams",false);
                    if(grams==null)grams=BigDecimal.ZERO;
                    if(grams.compareTo(BigDecimal.valueOf(3000))>0)
                        throw invalid("Food grams out of range");
                    String mode=edited?item.path("mode").asText("catalog"):"catalog";
                    if(!Set.of("catalog","manual","template").contains(mode))
                        throw invalid("Unknown energy source");
                    boolean manual="manual".equals(mode), template="template".equals(mode);
                    DishTemplate selectedTemplate=null;
                    if(template) {
                        long templateId=item.path("templateId").asLong(0);
                        if(templateId<=0) throw invalid("Personal dish not selected");
                        selectedTemplate=wellness.ownedDishTemplate(templateId);
                    }
                    BigDecimal manualCalories=null;
                    if(manual) {
                        manualCalories=decimal(item,"manualCalories",true);
                        if(manualCalories.signum()<=0 ||
                            manualCalories.compareTo(new BigDecimal("20000"))>0 ||
                            manualCalories.scale()>2)
                            throw invalid("Manual kcal must be between 0 and 20000");
                    }
                    if(template) manualCalories=selectedTemplate.caloriesPerServing();
                    Food match=null;
                    if(!manual && !template && edited && item.path("foodId").canConvertToLong() && item.path("foodId").asLong()>0)
                        match=wellness.accessibleFood(item.path("foodId").asLong());
                    if(!manual && !template && !edited) {
                        // Conservative name matching; do not silently equate similarly named recipes.
                        String normalized=normalize(name);
                        match=wellness.foods(name).stream()
                            .filter(f->normalize(f.name()).equals(normalized)).findFirst().orElse(null);
                    }
                    Map<String,Object> record=new LinkedHashMap<>();
                    record.put("foodId",match==null?0:match.id());
                    record.put("mode",template?"template":manual?"manual":"catalog");
                    record.put("name",template?selectedTemplate.dishName():match==null?name:match.name());
                    record.put("grams",template?BigDecimal.ZERO:grams);
                    record.put("templateId",template?selectedTemplate.id():null);
                    record.put("manualCalories",manualCalories);
                    record.put("calories",manual||template?manualCalories:match==null||grams.signum()==0?null:
                        NutritionMath.portion(match.calories100g(),grams));
                    if(edited && manual) {
                        boolean save=item.path("saveToFavorites").asBoolean(false);
                        String merchant=item.path("merchantName").asText("").strip();
                        String portion=item.path("portionLabel").asText("").strip();
                        String source=item.path("sourceType").asText("USER_ESTIMATE");
                        String sourceNote=item.path("sourceNote").asText("").strip();
                        int count=item.path("portionCount").isNull()||item.path("portionCount").asText("").isBlank()
                            ?0:item.path("portionCount").asInt(-1);
                        if(merchant.length()>100 || portion.length()>100 || sourceNote.length()>255 ||
                            !Set.of("USER_ESTIMATE","AI_ESTIMATE","LABEL","OTHER").contains(source) ||
                            count<0 || count>9999)
                            throw invalid("Invalid personal dish details");
                        record.put("saveToFavorites",save);
                        record.put("merchantName",merchant);
                        record.put("portionLabel",portion);
                        record.put("portionCount",count==0?null:count);
                        record.put("sourceType",source);
                        record.put("sourceNote",sourceNote);
                    }
                    parsed.add(record);
                }
                String note=node.path("note").asText("");
                if(note.length()>300)note=note.substring(0,300);
                m.put("mealType",type);m.put("items",parsed);m.put("note",note);
            }
            case "exercise.create" -> {
                String name=node.path("name").asText("").trim();
                int minutes=node.path("durationMinutes").asInt(-1);
                if(name.isEmpty()||name.length()>100||minutes<1||minutes>1440)
                    throw invalid("Exercise name/duration required");
                BigDecimal kcal=decimal(node,"estimatedKcal",false);
                if(kcal!=null&&kcal.compareTo(BigDecimal.valueOf(20000))>0)throw invalid("Exercise calories");
                m.put("name",name);m.put("durationMinutes",minutes);
                m.put("estimatedKcal",kcal==null?"":kcal.toPlainString());
                m.put("note",node.path("note").asText("").substring(0,
                    Math.min(300,node.path("note").asText("").length())));
            }
            case "metric.create" -> {
                BigDecimal weight=decimal(node,"weightKg",true);
                if(weight.compareTo(BigDecimal.valueOf(0.1))<0 ||
                    weight.compareTo(BigDecimal.valueOf(500))>0)throw invalid("Weight out of range");
                BigDecimal fat=decimal(node,"bodyFatPct",false);
                BigDecimal waist=decimal(node,"waistCm",false);
                if((fat!=null&&fat.compareTo(BigDecimal.valueOf(100))>0)||
                    (waist!=null&&waist.compareTo(BigDecimal.valueOf(300))>0))
                    throw invalid("Body metrics out of range");
                m.put("weightKg",weight);m.put("bodyFatPct",fat==null?"":fat.toPlainString());
                m.put("waistCm",waist==null?"":waist.toPlainString());
            }
            default -> throw invalid("Only new health records are currently supported by AI");
        }
        return m;
    }
    static String normalize(String name){
        return name.replaceAll("[\\s（）()]", "").toLowerCase(Locale.ROOT);
    }
    private String description(String action, Map<String,Object> values){
        String day=String.valueOf(values.get("date"));
        return switch(action){
            case "meal.create" -> day+" "+values.get("mealType")+" 饮食："+
                ((List<?>)values.get("items")).size()+" 种食物，核对重量后保存";
            case "exercise.create" -> day+" "+values.get("name")+"，"+values.get("durationMinutes")+" 分钟";
            case "metric.create" -> day+" 体重 "+values.get("weightKg")+" kg";
            default -> throw invalid("Unknown action");
        };
    }

    /**
     * Human changes are normalized again by server services, not trusted as model-authored
     * nutritional values. The action type is taken exclusively from the stored draft.
     */
    @Transactional
    public Preview edit(String draftId,JsonNode changes){
        long user=CurrentUser.id();
        if(draftId==null||!draftId.matches("[0-9a-fA-F-]{36}"))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Invalid draft");
        if(changes==null||!changes.isObject()||changes.toString().length()>5000)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Invalid draft corrections");
        List<Map<String,Object>> rows=db.queryForList(
            "SELECT action_type,status,expires_at,model_used FROM prp_wellness_ai_drafts " +
            "WHERE id=? AND user_id=? FOR UPDATE",draftId,user);
        if(rows.isEmpty())throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Draft not found");
        var row=rows.get(0);
        java.sql.Timestamp expires=(java.sql.Timestamp)row.get("expires_at");
        if(!"PENDING".equals(row.get("status"))||!expires.toLocalDateTime().isAfter(LocalDateTime.now()))
            throw new ResponseStatusException(HttpStatus.CONFLICT,"Draft expired or already used");
        String action=String.valueOf(row.get("action_type"));
        var safe=((com.fasterxml.jackson.databind.node.ObjectNode)changes.deepCopy()).put("action",action);
        Map<String,Object> checked=verify(safe,true);
        String description=description(action,checked);
        try {
            int updated=db.update("UPDATE prp_wellness_ai_drafts SET payload_json=?,description=? " +
                "WHERE id=? AND user_id=? AND status='PENDING'",
                json.writeValueAsString(checked),description,draftId,user);
            if(updated!=1)throw new ResponseStatusException(HttpStatus.CONFLICT,"Draft already used");
        }catch(com.fasterxml.jackson.core.JsonProcessingException e){
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Cannot encode draft corrections");
        }
        return new Preview(draftId,action,description,String.valueOf(row.get("model_used")),
            checked,expires.toLocalDateTime().toString());
    }
    @Transactional
    public Outcome confirm(String draftId){
        long user=CurrentUser.id();
        if(draftId==null||!draftId.matches("[0-9a-fA-F-]{36}"))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Invalid draft");
        List<Map<String,Object>> rows=db.queryForList(
            "SELECT action_type,payload_json,status,expires_at FROM prp_wellness_ai_drafts "+
            "WHERE id=? AND user_id=? FOR UPDATE",draftId,user);
        if(rows.isEmpty())throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Draft not found");
        Map<String,Object> row=rows.get(0);
        java.sql.Timestamp expires=(java.sql.Timestamp)row.get("expires_at");
        if(!"PENDING".equals(row.get("status"))||expires.toLocalDateTime().isBefore(LocalDateTime.now()))
            throw new ResponseStatusException(HttpStatus.CONFLICT,"Draft expired or already used");
        try {
            JsonNode data=json.readTree(String.valueOf(row.get("payload_json")));
            String date=data.path("date").asText();
            Object saved;
            String action=String.valueOf(row.get("action_type"));
            switch(action){
                case "meal.create_batch" -> {
                    LocalDate day;
                    try{day=LocalDate.parse(date);}
                    catch(Exception e){throw invalid("Invalid meal date");}
                    if(day.isBefore(today().minusYears(2)) || day.isAfter(today().plusDays(1)))
                        throw invalid("Meal date outside recording range");
                    var groups=data.path("meals");
                    if(!groups.isArray() || groups.isEmpty() || groups.size()>4)
                        throw invalid("Invalid meal batch");
                    // Serialize all meal confirmations for this account. This also protects
                    // multiple pending drafts from creating duplicate same-day meal types.
                    db.queryForObject("SELECT id FROM prp_users WHERE id=? FOR UPDATE",Long.class,user);
                    LinkedHashSet<String> types=new LinkedHashSet<>();
                    List<WellnessService.AiMealItem> all=new ArrayList<>();
                    for(var group:groups){
                        String type=group.path("mealType").asText("");
                        if(!Set.of("BREAKFAST","LUNCH","DINNER","SNACK").contains(type) || !types.add(type))
                            throw invalid("Duplicate/invalid meal type");
                        var foods=group.path("items");
                        if(!foods.isArray() || foods.isEmpty() || foods.size()>8)
                            throw invalid("Invalid meal items");
                        BigDecimal sum=BigDecimal.ZERO;
                        for(var item:foods){
                            if(item.path("foodId").asLong(-1)!=0 ||
                                !"manual".equals(item.path("mode").asText()))
                                throw invalid("Only explicit user calorie snapshots supported");
                            String name=item.path("name").asText("");
                            BigDecimal grams=decimal(item,"grams",true);
                            BigDecimal kcal=decimal(item,"manualCalories",true);
                            if(name.isBlank()||name.length()>120||grams.compareTo(new BigDecimal("3000"))>0||
                                kcal.signum()<=0||kcal.compareTo(new BigDecimal("20000"))>0||kcal.scale()>2)
                                throw invalid("Invalid calorie snapshot");
                            sum=sum.add(kcal);
                        }
                        BigDecimal total=decimal(group,"totalCalories",true);
                        if(sum.compareTo(total)!=0)
                            throw invalid("Meal total does not match its items");
                    }
                    for(var meal:wellness.meals(day))
                        if(types.contains(meal.mealType()))
                            throw new ResponseStatusException(HttpStatus.CONFLICT,
                                "目标日期已有相同餐次，请查看健康中心；本批次未新增记录");
                    List<Meal> savedMeals=new ArrayList<>();
                    int ordinal=0;
                    for(var group:groups){
                        List<WellnessService.AiMealItem> foods=new ArrayList<>();
                        for(var item:group.path("items"))
                            foods.add(new WellnessService.AiMealItem(null,item.path("name").asText(),
                                decimal(item,"grams",true),decimal(item,"manualCalories",true)));
                        // All inserts and CONSUMED transition are within this transaction.
                        String key=draftId+"-"+ordinal++;
                        savedMeals.add(wellness.addAiMeal(day,group.path("mealType").asText(),
                            group.path("note").asText("用户估算"),foods,key));
                    }
                    saved=savedMeals;
                }
                case "meal.copy_batch" -> {
                    var targetNodes=data.path("targets");
                    if(!targetNodes.isArray() || targetNodes.size()<1 || targetNodes.size()>7)
                        throw invalid("Invalid batch targets");
                    String type=data.path("mealType").asText("");
                    if(!Set.of("BREAKFAST","LUNCH","DINNER","SNACK").contains(type))
                        throw invalid("Invalid batch meal type");
                    long sourceId=data.path("sourceMealId").asLong(0);
                    if(sourceId<=0) throw invalid("Missing source meal");
                    var source=wellness.ownedMeal(sourceId); // enforces authenticated ownership
                    if(!source.mealDate().toString().equals(data.path("sourceDate").asText()) ||
                        !source.mealType().equals(type))
                        throw new ResponseStatusException(HttpStatus.CONFLICT,
                            "来源餐次发生变化，请重新创建批量草稿");
                    var snapshot=data.path("items");
                    if(!snapshot.isArray() || snapshot.size()!=source.items().size() ||
                        snapshot.isEmpty() || snapshot.size()>8)
                        throw new ResponseStatusException(HttpStatus.CONFLICT,
                            "来源食物与草稿不一致，请重新创建");
                    List<ItemInput> copied=new ArrayList<>();
                    List<WellnessService.AiMealItem> mixed=new ArrayList<>();
                    boolean hasCustom=false;
                    for(int i=0;i<source.items().size();i++) {
                        var original=source.items().get(i);
                        var expected=snapshot.get(i);
                        if(original.grams()==null ||
                            original.foodId()!=expected.path("foodId").asLong(-1) ||
                            !expected.path("grams").isNumber() ||
                            original.grams().compareTo(expected.path("grams").decimalValue())!=0)
                            throw new ResponseStatusException(HttpStatus.CONFLICT,
                                "来源餐次食物或份量已改变，请重新预览后确认");
                        if(original.foodId()>0) {
                            wellness.accessibleFood(original.foodId());
                            copied.add(new ItemInput(original.foodId(),original.grams()));
                            mixed.add(new WellnessService.AiMealItem(original.foodId(),null,original.grams(),null));
                        } else {
                            if(!"manual".equals(expected.path("mode").asText("")) ||
                                !original.foodName().equals(expected.path("name").asText()) ||
                                !expected.path("manualCalories").isNumber() ||
                                original.calories()==null ||
                                original.calories().compareTo(expected.path("manualCalories").decimalValue())!=0)
                                throw new ResponseStatusException(HttpStatus.CONFLICT,
                                    "来源自定义热量已改变，请重新预览后确认");
                            hasCustom=true;
                            mixed.add(new WellnessService.AiMealItem(null,original.foodName(),
                                original.grams(),original.calories()));
                        }
                    }
                    LinkedHashSet<LocalDate> targets=new LinkedHashSet<>();
                    LocalDate now=today();
                    for(JsonNode target:targetNodes) {
                        LocalDate day;
                        try { day=LocalDate.parse(target.asText()); }
                        catch(Exception e){ throw invalid("Invalid target date"); }
                        if(!day.isBefore(now) || day.isBefore(now.minusYears(2)) ||
                            day.equals(source.mealDate()) || !targets.add(day))
                            throw invalid("Invalid or duplicated target date");
                        if(wellness.meals(day).stream().anyMatch(m->m.mealType().equals(type)))
                            throw new ResponseStatusException(HttpStatus.CONFLICT,
                                day+" 已有该餐次，本次未新增任何记录");
                    }
                    if(targets.size()!=targetNodes.size() ||
                        !targets.iterator().next().toString().equals(date))
                        throw invalid("Batch target/date mismatch");
                    List<Meal> savedMeals=new ArrayList<>();
                    int index=0;
                    for(var day:targets) {
                        // Unique per-draft + per-day key, in the same transaction as draft consumption.
                        String key=draftId+"-"+index++;
                        if(hasCustom)
                            savedMeals.add(wellness.addAiMeal(day,type,source.note(),mixed,key));
                        else
                            savedMeals.add(wellness.addMeal(new MealInput(day,type,source.note(),copied,key)));
                    }
                    saved=savedMeals;
                }
                case "meal.create" -> {
                    LocalDate target=LocalDate.parse(date);
                    String targetType=data.path("mealType").asText("");
                    if(!Set.of("BREAKFAST","LUNCH","DINNER","SNACK").contains(targetType))
                        throw invalid("Invalid meal type");
                    db.queryForObject("SELECT id FROM prp_users WHERE id=? FOR UPDATE",Long.class,user);
                    if(wellness.meals(target).stream().anyMatch(m->m.mealType().equals(targetType)))
                        throw new ResponseStatusException(HttpStatus.CONFLICT,
                            "该日期的餐次已存在，请在健康中心查看或编辑，不能重复保存");
                    List<ItemInput> catalogItems=new ArrayList<>();
                    List<WellnessService.AiMealItem> snapshots=new ArrayList<>();
                    boolean hasManual=false;
                    for(JsonNode item:data.path("items")) {
                        String mode=item.path("mode").asText("catalog");
                        long foodId=item.path("foodId").asLong(0);
                        BigDecimal grams=item.path("grams").decimalValue();
                        if("manual".equals(mode) || "template".equals(mode)) {
                            if(foodId!=0) throw invalid("Custom entries may not reference catalog foods");
                            BigDecimal kcal=decimal(item,"manualCalories",true);
                            if(kcal.signum()<=0 || kcal.compareTo(new BigDecimal("20000"))>0 ||
                                kcal.scale()>2 || grams.signum()<0 || grams.compareTo(new BigDecimal("3000"))>0)
                                throw invalid("Invalid custom food calories");
                            String name=item.path("name").asText("");
                            if("template".equals(mode)) {
                                DishTemplate source=wellness.ownedDishTemplate(item.path("templateId").asLong(0));
                                if(kcal.compareTo(source.caloriesPerServing())!=0 ||
                                    !name.equals(source.dishName()))
                                    throw new ResponseStatusException(HttpStatus.CONFLICT,
                                        "常吃餐品已修改，请重新选择模板后确认");
                                name=source.dishName();
                            } else if(item.path("saveToFavorites").asBoolean(false)) {
                                String merchant=item.path("merchantName").asText("");
                                String portion=item.path("portionLabel").asText("");
                                Integer count=item.path("portionCount").isNumber()
                                    ?item.path("portionCount").asInt():null;
                                wellness.saveDishTemplate(new DishTemplateInput(merchant,name,portion,
                                    count,kcal,item.path("sourceType").asText("USER_ESTIMATE"),
                                    item.path("sourceNote").asText("")));
                            }
                            snapshots.add(new WellnessService.AiMealItem(null,name,grams,kcal));
                            hasManual=true;
                        } else {
                            if(foodId<=0||grams.signum()<=0)
                                throw invalid("Please select a catalog food and valid weight, or use custom calories");
                            catalogItems.add(new ItemInput(foodId,grams));
                            snapshots.add(new WellnessService.AiMealItem(foodId,null,grams,null));
                        }
                    }
                    String note=data.path("note").asText("");
                    if(hasManual) {
                        String marker="用户自定义热量（营养素未知）";
                        note=(note.isBlank()?marker:note+"；"+marker);
                        if(note.length()>500)note=note.substring(0,500);
                        saved=wellness.addAiMeal(LocalDate.parse(date),data.path("mealType").asText(),
                            note,snapshots,draftId);
                    } else saved=wellness.addMeal(new MealInput(LocalDate.parse(date),
                        data.path("mealType").asText(),note,catalogItems,draftId));
                }
                case "exercise.create" -> {
                    String raw=data.path("estimatedKcal").asText("");
                    saved=wellness.addExercise(new ExerciseInput(LocalDate.parse(date),data.path("name").asText(),
                        data.path("durationMinutes").asInt(),raw.isBlank()?null:new BigDecimal(raw),
                        data.path("note").asText("")));
                }
                case "metric.create" -> {
                    String fat=data.path("bodyFatPct").asText("");
                    String waist=data.path("waistCm").asText("");
                    saved=wellness.addMetric(new BodyMetricInput(LocalDate.parse(date),
                        new BigDecimal(data.path("weightKg").asText()),
                        fat.isBlank()?null:new BigDecimal(fat),
                        waist.isBlank()?null:new BigDecimal(waist)));
                }
                default -> throw invalid("Invalid draft action");
            }
            int changed=db.update("UPDATE prp_wellness_ai_drafts SET status='CONSUMED',consumed_at=NOW() "+
                "WHERE id=? AND user_id=? AND status='PENDING'",draftId,user);
            if(changed!=1)throw new ResponseStatusException(HttpStatus.CONFLICT,"Draft already used");
            return new Outcome(action,saved,"/wellness?date="+date);
        }catch(ResponseStatusException e){throw e;}
         catch(Exception e){throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY,
             "Record could not be saved; check food catalog and draft fields");}
    }
}
