package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import org.springframework.jdbc.core.JdbcTemplate;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("video-integration")
class WellnessDatabaseIT {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;
    @Autowired JdbcTemplate jdbc;

    private MockHttpServletRequestBuilder auth(MockHttpServletRequestBuilder req, String token) {
        return req.header(HttpHeaders.AUTHORIZATION, "Bearer " + token);
    }
    private JsonNode postJson(String url, String token, Object body) throws Exception {
        MockHttpServletRequestBuilder req=post(url).contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsBytes(body));
        if(token!=null) req=auth(req,token);
        return mapper.readTree(mvc.perform(req).andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString()).path("data");
    }
    private JsonNode getData(String url, String token) throws Exception {
        return mapper.readTree(mvc.perform(auth(get(url),token)).andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString()).path("data");
    }
    private String login(String username,String password) throws Exception {
        return postJson("/api/auth/login",null,Map.of("username",username,"password",password))
                .path("token").asText();
    }
    @Test void mealNutritionSnapshotIdempotencyAndTenantIsolation() throws Exception {
        String a=login("video_admin","video-test-admin-password-2026");
        mvc.perform(get("/api/wellness/meals?date=2026-10-11")).andExpect(status().isUnauthorized());

        JsonNode f=postJson("/api/wellness/foods",a,Map.of(
                "name","Private bowl","preparation","cooked","calories100g",125,
                "protein100g",12,"carbs100g",10,"fat100g",4,"sourceNote","test"));
        long foodId=f.path("id").asLong();
        Map<String,Object> validItem=Map.of("foodId",foodId,"grams",200);
        Map<String,Object> meal=Map.of("mealDate","2026-10-11","mealType","LUNCH",
                "items",List.of(validItem),"idempotencyKey","wellness-integration-once");
        JsonNode first=postJson("/api/wellness/meals",a,meal);
        assertThat(first.path("items").get(0).path("calories").decimalValue())
                .isEqualByComparingTo("250.00");
        assertThat(postJson("/api/wellness/meals",a,meal).path("id").asLong())
                .isEqualTo(first.path("id").asLong());
        long mealId=first.path("id").asLong();
        assertThat(getData("/api/wellness/foods/frequent",a).get(0).path("id").asLong()).isEqualTo(foodId);
        JsonNode summary=getData("/api/wellness/summary/daily?date=2026-10-11",a);
        assertThat(summary.path("calories").decimalValue()).isEqualByComparingTo("250.00");
        assertThat(summary.path("mealCount").asInt()).isEqualTo(1);

        String invite=postJson("/api/auth/invitations",a,Map.of()).path("code").asText();
        String b=postJson("/api/auth/register",null,Map.of(
                "username","wellness_friend_case","password","friend-password-2026",
                "displayName","Second User","invitationCode",invite)).path("token").asText();
        assertThat(getData("/api/wellness/meals?date=2026-10-11",b).size()).isZero();
        assertThat(getData("/api/wellness/foods/frequent",b).size()).isZero();
        assertThat(getData("/api/wellness/foods?q=Private%20bowl",b).size()).isZero();
        mvc.perform(auth(delete("/api/wellness/meals/{id}",mealId),b)).andExpect(status().isNotFound());
        mvc.perform(auth(post("/api/wellness/meals/{id}/copy?date=2026-10-11",mealId),b))
                .andExpect(status().isNotFound());
        mvc.perform(auth(put("/api/wellness/meals/{id}",mealId).contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsBytes(meal)),b)).andExpect(status().isNotFound());
        mvc.perform(auth(post("/api/wellness/meals").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsBytes(Map.of("mealDate","2026-10-11","mealType","LUNCH",
                        "items",List.of(validItem)))),b)).andExpect(status().isNotFound());

        // A rejected second line item must roll back the whole newly inserted meal.
        JsonNode before=getData("/api/wellness/meals?date=2026-10-11",a);
        mvc.perform(auth(post("/api/wellness/meals").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsBytes(Map.of("mealDate","2026-10-11","mealType","DINNER",
                        "items",List.of(validItem,Map.of("foodId",Long.MAX_VALUE,"grams",100))))),a))
                .andExpect(status().isNotFound());
        assertThat(getData("/api/wellness/meals?date=2026-10-11",a).size()).isEqualTo(before.size());

        JsonNode noRecords=getData("/api/wellness/summary/daily?date=2026-01-01",b);
        assertThat(noRecords.path("calories").isNull()).isTrue();
    }
    @Test void twoIndependentAiDraftsCannotWriteSameMealConcurrently() throws Exception {
        String token=login("video_admin","video-test-admin-password-2026");
        Long userId=jdbc.queryForObject("SELECT id FROM prp_users WHERE username=?",Long.class,"video_admin");
        String date="2026-09-27";
        String payload=mapper.writeValueAsString(Map.of(
                "date",date,"meals",List.of(Map.of(
                    "mealType","DINNER","totalCalories",105,
                    "items",List.of(Map.of("foodId",0,"mode","manual",
                            "name","P0 concurrency yogurt","grams",135,"manualCalories",105))))));
        String first=UUID.randomUUID().toString(),second=UUID.randomUUID().toString();
        for(String id:List.of(first,second)) {
            jdbc.update("INSERT INTO prp_wellness_ai_drafts " +
                            "(id,user_id,action_type,payload_json,description,model_used,expires_at) " +
                            "VALUES (?,?,?,?,?,?,?)",id,userId,"meal.create_batch",payload,
                    "Concurrent meal protection","test",Timestamp.valueOf(LocalDateTime.now().plusMinutes(10)));
        }
        CountDownLatch start=new CountDownLatch(1);
        var pool=Executors.newFixedThreadPool(2);
        try {
            var a=pool.submit(()->{
                start.await();
                return mvc.perform(auth(post("/api/wellness/ai/drafts/{id}/confirm",first),token))
                        .andReturn().getResponse().getStatus();
            });
            var b=pool.submit(()->{
                start.await();
                return mvc.perform(auth(post("/api/wellness/ai/drafts/{id}/confirm",second),token))
                        .andReturn().getResponse().getStatus();
            });
            start.countDown();
            int s1=a.get(20,TimeUnit.SECONDS),s2=b.get(20,TimeUnit.SECONDS);
            assertThat(List.of(s1,s2)).containsExactlyInAnyOrder(200,409);
            Long meals=jdbc.queryForObject(
                    "SELECT COUNT(*) FROM prp_wellness_meals WHERE user_id=? AND meal_date=? AND meal_type='DINNER'",
                    Long.class,userId,date);
            assertThat(meals).isEqualTo(1L);
            Long consumed=jdbc.queryForObject(
                    "SELECT COUNT(*) FROM prp_wellness_ai_drafts WHERE id IN (?,?) AND status='CONSUMED'",
                    Long.class,first,second);
            assertThat(consumed).isEqualTo(1L);
        } finally {
            pool.shutdownNow();
        }
    }


    @Test void savedAiActionTargetsFollowRealRecordsAndEnforceOwnership() throws Exception {
        String a=login("video_admin","video-test-admin-password-2026");
        Long userId=jdbc.queryForObject("SELECT id FROM prp_users WHERE username=?",Long.class,"video_admin");
        String draftId=UUID.randomUUID().toString();
        String date="2026-09-26";
        String payload=mapper.writeValueAsString(Map.of(
            "date",date,"meals",List.of(Map.of("mealType","BREAKFAST","totalCalories",105,
                "items",List.of(Map.of("foodId",0,"mode","manual",
                    "name","Draft target test yogurt","grams",135,"manualCalories",105))))));
        jdbc.update("INSERT INTO prp_wellness_ai_drafts " +
            "(id,user_id,action_type,payload_json,description,model_used,expires_at) VALUES (?,?,?,?,?,?,?)",
            draftId,userId,"meal.create_batch",payload,"Linked test record","test",
            Timestamp.valueOf(LocalDateTime.now().plusMinutes(10)));
        String url="/api/wellness/ai/drafts/"+draftId+"/targets";
        assertThat(getData(url,a).size()).isZero();
        JsonNode saved=postJson("/api/wellness/ai/drafts/"+draftId+"/confirm",a,Map.of());
        long id=saved.path("saved").get(0).path("id").asLong();
        assertThat(id).isPositive();
        JsonNode targets=getData(url,a);
        assertThat(targets.size()).isEqualTo(1);
        assertThat(targets.get(0).path("recordId").asLong()).isEqualTo(id);
        assertThat(targets.get(0).path("record").path("items").get(0).path("foodName").asText())
            .isEqualTo("Draft target test yogurt");
        assertThat(targets.get(0).path("deleted").asBoolean()).isFalse();
        mvc.perform(auth(post("/api/wellness/ai/drafts/{id}/confirm",draftId),a))
            .andExpect(status().isConflict());
        mvc.perform(auth(put("/api/wellness/meals/{id}/snapshots",id)
            .contentType(MediaType.APPLICATION_JSON)
            .content(mapper.writeValueAsBytes(Map.of("mealDate",date,"mealType","BREAKFAST",
                "note","Changed after AI confirmation",
                "items",List.of(Map.of("foodId",0,"name","Changed meal","grams",135,"calories",115))))),a))
            .andExpect(status().isOk());
        assertThat(getData(url,a).get(0).path("record").path("note").asText())
            .isEqualTo("Changed after AI confirmation");
        String invite=postJson("/api/auth/invitations",a,Map.of()).path("code").asText();
        String outsider=postJson("/api/auth/register",null,Map.of(
            "username","ai_action_guest_"+UUID.randomUUID().toString().substring(0,8),
            "password","guest-password-2026", "displayName","Guest",
            "invitationCode",invite)).path("token").asText();
        mvc.perform(auth(get(url),outsider)).andExpect(status().isNotFound());
        mvc.perform(auth(delete("/api/wellness/meals/{id}",id),a)).andExpect(status().isOk());
        JsonNode missing=getData(url,a);
        assertThat(missing.get(0).path("deleted").asBoolean()).isTrue();
        assertThat(missing.get(0).path("record").isNull()).isTrue();
    }

}
