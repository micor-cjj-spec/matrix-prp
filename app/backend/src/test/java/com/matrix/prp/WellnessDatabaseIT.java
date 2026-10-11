package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
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
        JsonNode summary=getData("/api/wellness/summary/daily?date=2026-10-11",a);
        assertThat(summary.path("calories").decimalValue()).isEqualByComparingTo("250.00");
        assertThat(summary.path("mealCount").asInt()).isEqualTo(1);

        String invite=postJson("/api/auth/invitations",a,Map.of()).path("code").asText();
        String b=postJson("/api/auth/register",null,Map.of(
                "username","wellness_friend_case","password","friend-password-2026",
                "displayName","Second User","invitationCode",invite)).path("token").asText();
        assertThat(getData("/api/wellness/meals?date=2026-10-11",b).size()).isZero();
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
}
