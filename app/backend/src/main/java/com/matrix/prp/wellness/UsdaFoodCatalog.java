package com.matrix.prp.wellness;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

/** Opt-in CC0 USDA FoodData Central lookup. No query or model-supplied URLs are fetched. */
@Service
public class UsdaFoodCatalog {
    public record Candidate(long fdcId, String name, BigDecimal calories100g,
                            BigDecimal protein100g, BigDecimal carbs100g, BigDecimal fat100g,
                            String source) {}
    private final String key;
    private final ObjectMapper mapper;
    private final HttpClient client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5))
        .followRedirects(HttpClient.Redirect.NEVER).build();

    public UsdaFoodCatalog(@Value("${matrix-prp.wellness.usda-api-key:}") String key, ObjectMapper mapper) {
        this.key = key; this.mapper = mapper;
    }
    /** Only these unambiguous ingredient names are translated; composite dishes are not silently approximated. */
    private static final java.util.Map<String,String> CHINESE_SEARCH = java.util.Map.ofEntries(
        Map.entry("米饭","rice white cooked"),
        Map.entry("大米","rice white"),
        Map.entry("糙米","brown rice cooked"),
        Map.entry("小米","millet cooked"),
        Map.entry("燕麦","oats"),
        Map.entry("燕麦片","rolled oats"),
        Map.entry("面包","bread"),
        Map.entry("全麦面包","whole wheat bread"),
        Map.entry("馒头","steamed bun"),
        Map.entry("面条","noodles cooked"),
        Map.entry("意大利面","pasta cooked"),
        Map.entry("米粉","rice noodles"),
        Map.entry("土豆","potato"),
        Map.entry("红薯","sweet potato"),
        Map.entry("玉米","sweet corn"),
        Map.entry("南瓜","pumpkin"),
        Map.entry("山药","yam"),
        Map.entry("鸡蛋","egg"),
        Map.entry("鸡蛋白","egg white"),
        Map.entry("鸡蛋黄","egg yolk"),
        Map.entry("牛奶","milk whole"),
        Map.entry("脱脂牛奶","milk nonfat"),
        Map.entry("酸奶","yogurt"),
        Map.entry("无糖酸奶","yogurt plain unsweetened"),
        Map.entry("希腊酸奶","greek yogurt plain"),
        Map.entry("奶酪","cheese"),
        Map.entry("黄油","butter"),
        Map.entry("鸡胸肉","chicken breast"),
        Map.entry("鸡腿","chicken thigh"),
        Map.entry("鸡翅","chicken wing"),
        Map.entry("牛肉","beef"),
        Map.entry("牛里脊","beef tenderloin"),
        Map.entry("猪肉","pork"),
        Map.entry("猪里脊","pork tenderloin"),
        Map.entry("羊肉","lamb"),
        Map.entry("鸭肉","duck"),
        Map.entry("三文鱼","salmon"),
        Map.entry("鳕鱼","cod"),
        Map.entry("鲈鱼","sea bass"),
        Map.entry("金枪鱼","tuna"),
        Map.entry("虾仁","shrimp"),
        Map.entry("花甲","clam"),
        Map.entry("扇贝","scallops"),
        Map.entry("鱿鱼","squid"),
        Map.entry("豆腐","tofu"),
        Map.entry("老豆腐","firm tofu"),
        Map.entry("嫩豆腐","soft tofu"),
        Map.entry("豆腐干","dried tofu"),
        Map.entry("黄豆","soybeans"),
        Map.entry("毛豆","edamame"),
        Map.entry("绿豆","mung beans"),
        Map.entry("红豆","adzuki beans"),
        Map.entry("鹰嘴豆","chickpeas"),
        Map.entry("西兰花","broccoli"),
        Map.entry("黄瓜","cucumber"),
        Map.entry("菠菜","spinach"),
        Map.entry("生菜","lettuce"),
        Map.entry("卷心菜","cabbage"),
        Map.entry("大白菜","napa cabbage"),
        Map.entry("胡萝卜","carrots"),
        Map.entry("番茄","tomato"),
        Map.entry("西红柿","tomato"),
        Map.entry("茄子","eggplant"),
        Map.entry("洋葱","onion"),
        Map.entry("青椒","bell pepper"),
        Map.entry("蘑菇","mushrooms"),
        Map.entry("香菇","shiitake mushrooms"),
        Map.entry("金针菇","enoki mushrooms"),
        Map.entry("海带","kelp"),
        Map.entry("香蕉","banana"),
        Map.entry("苹果","apple"),
        Map.entry("梨","pear"),
        Map.entry("橙子","orange"),
        Map.entry("葡萄","grapes"),
        Map.entry("草莓","strawberries"),
        Map.entry("蓝莓","blueberries"),
        Map.entry("西瓜","watermelon"),
        Map.entry("芒果","mango"),
        Map.entry("猕猴桃","kiwifruit"),
        Map.entry("菠萝","pineapple"),
        Map.entry("桃子","peach"),
        Map.entry("牛油果","avocado"),
        Map.entry("花生","peanuts"),
        Map.entry("核桃","walnuts"),
        Map.entry("杏仁","almonds"),
        Map.entry("腰果","cashews"),
        Map.entry("花生油","peanut oil"),
        Map.entry("菜籽油","canola oil"),
        Map.entry("橄榄油","olive oil"),
        Map.entry("蜂蜜","honey"),
        Map.entry("白糖","sugar")
    );
    static String normalizeQuery(String query) {
        return CHINESE_SEARCH.getOrDefault(query.trim(),query.trim());
    }

    public boolean configured() { return key != null && !key.isBlank(); }
    private JsonNode fetch(String path) {
        if (!configured()) throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
            "USDA API key not configured; local foods remain available");
        try {
            URI url=URI.create("https://api.nal.usda.gov/fdc/v1/" + path +
                (path.contains("?") ? "&" : "?") + "api_key=" + URLEncoder.encode(key, StandardCharsets.UTF_8));
            HttpRequest req=HttpRequest.newBuilder(url).timeout(Duration.ofSeconds(8))
                .header("User-Agent","MatrixPRP/1.0 (https://github.com/micor-cjj-spec/matrix-prp)")
                .GET().build();
            HttpResponse<String> response=client.send(req,HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            if(response.statusCode()!=200) throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,
                "USDA unavailable (" + response.statusCode() + ")");
            if(response.body().length()>1_500_000) throw new IllegalArgumentException("USDA response too large");
            return mapper.readTree(response.body());
        } catch(ResponseStatusException e){throw e;}
          catch(Exception e){throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,"USDA search failed");}
    }
    public List<Candidate> search(String query) {
        if(query==null || query.isBlank() || query.length()>80 ||
            !query.matches("[\\p{L}0-9 ,.'()/-]+"))
            throw new IllegalArgumentException("Enter a food name (1-80 characters)");
        JsonNode json=fetch("foods/search?query="+URLEncoder.encode(normalizeQuery(query),StandardCharsets.UTF_8)+
            "&pageSize=20&dataType=Foundation,SR%20Legacy,Survey%20(FNDDS),Branded");
        List<Candidate> items=new ArrayList<>();
        for(JsonNode food:json.path("foods")){
            Candidate item=parse(food);
            if(item!=null) items.add(item);
        }
        return items;
    }
    public Candidate detail(long id) {
        if(id<=0) throw new IllegalArgumentException("Invalid FDC ID");
        Candidate item=parse(fetch("food/"+id));
        if(item==null || item.fdcId()!=id) throw new ResponseStatusException(
            HttpStatus.UNPROCESSABLE_ENTITY,"USDA record lacks complete per-100g nutrients");
        return item;
    }
    static Candidate parse(JsonNode node) {
        long id=node.path("fdcId").asLong(0);
        String name=node.path("description").asText("").trim();
        if(id<=0 || name.isBlank() || name.length()>120) return null;
        BigDecimal energy=nutrient(node,"208","1008","2047","2048");
        BigDecimal protein=nutrient(node,"203","1003");
        BigDecimal carbs=nutrient(node,"205","1005");
        BigDecimal fat=nutrient(node,"204","1004");
        if(energy==null || protein==null || carbs==null || fat==null ||
           energy.signum()<0 || energy.compareTo(BigDecimal.valueOf(900))>0 ||
           protein.signum()<0 || carbs.signum()<0 || fat.signum()<0 ||
           protein.compareTo(BigDecimal.valueOf(100))>0 ||
           carbs.compareTo(BigDecimal.valueOf(100))>0 ||
           fat.compareTo(BigDecimal.valueOf(100))>0) return null;
        return new Candidate(id,name,energy,protein,carbs,fat,"USDA FoodData Central CC0 · FDC #"+id);
    }
    static BigDecimal nutrient(JsonNode node,String... ids){
        for(JsonNode v:node.path("foodNutrients")){
            JsonNode n=v.path("nutrient");
            String number=v.path("nutrientNumber").asText(v.path("number").asText(n.path("number").asText("")));
            String id=v.path("nutrientId").asText(n.path("id").asText(""));
            for(String requested:ids) if(requested.equals(number)||requested.equals(id)){
                String unit=v.path("unitName").asText(n.path("unitName").asText(""));
                if((requested.equals("208")||requested.equals("1008")||
                    requested.equals("2047")||requested.equals("2048")) &&
                    !unit.equalsIgnoreCase("kcal")) continue;
                JsonNode value=v.hasNonNull("value") ? v.path("value") : v.path("amount");
                if(value.isNumber()) return value.decimalValue();
            }
        }
        return null;
    }
}
