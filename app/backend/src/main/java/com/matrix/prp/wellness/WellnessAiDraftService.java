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
public class WellnessAiDraftService {
    public record Preview(String draftId, String action, String description,
                          String modelUsed, Map<String,Object> values, String expiresAt) {}
    public record Outcome(String action, Object saved, String route) {}
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
                "若日期未指定用"+today()+"。餐次类型按时间与语义判断；纯文字缺克数时不要伪造，缺克数输出0以便服务端拒绝；照片可粗略估量分量（克）但务必提示用户核对，"+
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
    private Map<String,Object> verify(JsonNode node){
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
                    BigDecimal grams=decimal(item,"grams",true);
                    if(grams.compareTo(BigDecimal.valueOf(0.1))<0||grams.compareTo(BigDecimal.valueOf(3000))>0)
                        throw invalid("Food grams missing or out of range");
                    // The LLM may suggest names but it may not invent nutrient values.
                    List<Food> found=wellness.foods(name);
                    Food match=found.stream().filter(f->f.name().equals(name)).findFirst().orElse(null);
                    if(match==null)throw invalid("Food not in local catalog: "+name);
                    parsed.add(Map.of("foodId",match.id(),"name",match.name(),"grams",grams,
                        "calories",com.matrix.prp.wellness.NutritionMath.portion(match.calories100g(),grams)));
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
                case "meal.create" -> {
                    List<ItemInput> items=new ArrayList<>();
                    for(JsonNode item:data.path("items"))
                        items.add(new ItemInput(item.path("foodId").asLong(),item.path("grams").decimalValue()));
                    saved=wellness.addMeal(new MealInput(LocalDate.parse(date),
                        data.path("mealType").asText(),data.path("note").asText(""),items,draftId));
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
