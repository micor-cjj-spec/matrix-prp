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
        JsonNode json=fetch("foods/search?query="+URLEncoder.encode(query.trim(),StandardCharsets.UTF_8)+
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
