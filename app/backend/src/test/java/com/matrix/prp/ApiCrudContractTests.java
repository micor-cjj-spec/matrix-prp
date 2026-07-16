package com.matrix.prp;

import static org.hamcrest.Matchers.emptyOrNullString;
import static org.hamcrest.Matchers.greaterThanOrEqualTo;
import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

@ActiveProfiles("test")
@AutoConfigureMockMvc
@SpringBootTest
class ApiCrudContractTests {

    private static final String FIXED_DATE = "2026-07-14";
    private static final String FIXED_MONTH = "2026-07";

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Test
    void moduleAndTagApisUseStableContracts() throws Exception {
        String token = loginToken();

        mockMvc.perform(get("/api/modules/features")
                        .header(HttpHeaders.AUTHORIZATION, bearer(token)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value("SUCCESS"))
                .andExpect(jsonPath("$.data[?(@.code == 'records')]").exists())
                .andExpect(jsonPath("$.data[?(@.code == 'finance')]").exists());

        mockMvc.perform(get("/api/modules/domains")
                        .header(HttpHeaders.AUTHORIZATION, bearer(token)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value("SUCCESS"))
                .andExpect(jsonPath("$.data[?(@.code == 'life')]").exists())
                .andExpect(jsonPath("$.data[?(@.code == 'work')]").exists());

        long tagId = postAndReadId("/api/tags", token,
                "{\"name\":\"api-crud\",\"color\":\"#2563eb\",\"description\":\"API CRUD tag\"}");

        mockMvc.perform(get("/api/tags")
                        .header(HttpHeaders.AUTHORIZATION, bearer(token)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[?(@.id == %s)].name".formatted(tagId)).value("api-crud"));

        mockMvc.perform(put("/api/tags/{id}", tagId)
                        .header(HttpHeaders.AUTHORIZATION, bearer(token))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"api-crud-updated\",\"color\":\"#0f766e\",\"description\":\"Updated tag\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.id").value(tagId))
                .andExpect(jsonPath("$.data.name").value("api-crud-updated"));

        mockMvc.perform(delete("/api/tags/{id}", tagId)
                        .header(HttpHeaders.AUTHORIZATION, bearer(token)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value("SUCCESS"));
    }

    @Test
    void recordTaskFinanceAndReviewApisSupportCrudAndFilters() throws Exception {
        String token = loginToken();
        long tagId = postAndReadId("/api/tags", token,
                "{\"name\":\"flow-tag\",\"color\":\"#9333ea\",\"description\":\"Flow tag\"}");

        long recordId = postAndReadId("/api/records", token,
                """
                {"moduleCode":"work","title":"API record","content":"contract record body","recordDate":"%s","tagIds":[%d]}
                """.formatted(FIXED_DATE, tagId));
        mockMvc.perform(get("/api/records")
                        .queryParam("moduleCode", "work")
                        .queryParam("tagId", String.valueOf(tagId))
                        .queryParam("keyword", "contract")
                        .header(HttpHeaders.AUTHORIZATION, bearer(token)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data", hasSize(1)))
                .andExpect(jsonPath("$.data[0].id").value(recordId));
        mockMvc.perform(put("/api/records/{id}", recordId)
                        .header(HttpHeaders.AUTHORIZATION, bearer(token))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"moduleCode":"learning","title":"Updated API record","content":"updated body","recordDate":"%s","tagIds":[%d]}
                                """.formatted(FIXED_DATE, tagId)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.moduleCode").value("learning"));

        long taskId = postAndReadId("/api/tasks", token,
                """
                {"moduleCode":"work","title":"API task","description":"contract task","priority":"high","dueDate":"%s"}
                """.formatted(LocalDate.now().plusDays(1)));
        mockMvc.perform(get("/api/tasks")
                        .queryParam("status", "todo")
                        .queryParam("moduleCode", "work")
                        .queryParam("priority", "high")
                        .header(HttpHeaders.AUTHORIZATION, bearer(token)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data", hasSize(1)))
                .andExpect(jsonPath("$.data[0].id").value(taskId));
        mockMvc.perform(get("/api/tasks/summary")
                        .header(HttpHeaders.AUTHORIZATION, bearer(token)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value("SUCCESS"))
                .andExpect(jsonPath("$.data.openCount").value(greaterThanOrEqualTo(1)))
                .andExpect(jsonPath("$.data.upcomingSevenDaysCount").value(greaterThanOrEqualTo(1)))
                .andExpect(jsonPath("$.data.highPriorityOpenCount").value(greaterThanOrEqualTo(1)))
                .andExpect(jsonPath("$.data.statusCounts.todo").value(greaterThanOrEqualTo(1)));
        mockMvc.perform(patch("/api/tasks/{id}/status", taskId)
                        .queryParam("status", "done")
                        .header(HttpHeaders.AUTHORIZATION, bearer(token)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.status").value("done"));

        long transactionId = postAndReadId("/api/finance/transactions", token,
                """
                {"type":"expense","amount":42.50,"category":"tools","account":"cash","merchant":"store","note":"contract finance","transactionDate":"%s"}
                """.formatted(FIXED_DATE));
        long accountId = postAndReadId("/api/finance/accounts", token,
                """
                {"name":"cash","type":"cash","currency":"CNY","openingBalance":100.00,"note":"daily wallet"}
                """);
        long categoryId = postAndReadId("/api/finance/categories", token,
                """
                {"name":"tools","type":"expense","color":"#0f766e","note":"work tools"}
                """);
        mockMvc.perform(get("/api/finance/accounts")
                        .header(HttpHeaders.AUTHORIZATION, bearer(token)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[?(@.id == %s)].name".formatted(accountId)).value("cash"));
        mockMvc.perform(put("/api/finance/accounts/{id}", accountId)
                        .header(HttpHeaders.AUTHORIZATION, bearer(token))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"name":"bank","type":"bank","currency":"CNY","openingBalance":200.00,"note":"main bank"}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.name").value("bank"))
                .andExpect(jsonPath("$.data.type").value("bank"));
        mockMvc.perform(get("/api/finance/categories")
                        .queryParam("type", "expense")
                        .header(HttpHeaders.AUTHORIZATION, bearer(token)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[?(@.id == %s)].name".formatted(categoryId)).value("tools"));
        mockMvc.perform(put("/api/finance/categories/{id}", categoryId)
                        .header(HttpHeaders.AUTHORIZATION, bearer(token))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"name":"salary","type":"income","color":"#2563eb","note":"income category"}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.name").value("salary"))
                .andExpect(jsonPath("$.data.type").value("income"));
        mockMvc.perform(get("/api/finance/transactions")
                        .queryParam("month", FIXED_MONTH)
                        .queryParam("type", "expense")
                        .queryParam("category", "tools")
                        .header(HttpHeaders.AUTHORIZATION, bearer(token)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data", hasSize(1)))
                .andExpect(jsonPath("$.data[0].id").value(transactionId));
        mockMvc.perform(get("/api/finance/summary/monthly/categories")
                        .queryParam("month", FIXED_MONTH)
                        .header(HttpHeaders.AUTHORIZATION, bearer(token)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[0].category").value("tools"));
        mockMvc.perform(get("/api/finance/summary/monthly/accounts")
                        .queryParam("month", FIXED_MONTH)
                        .header(HttpHeaders.AUTHORIZATION, bearer(token)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[0].account").value("cash"))
                .andExpect(jsonPath("$.data[0].expense").value(42.50));
        mockMvc.perform(put("/api/finance/transactions/{id}", transactionId)
                        .header(HttpHeaders.AUTHORIZATION, bearer(token))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"type":"income","amount":300.00,"category":"salary","account":"bank","merchant":"client","note":"updated finance","transactionDate":"%s"}
                                """.formatted(FIXED_DATE)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.type").value("income"));

        long reviewId = postAndReadId("/api/reviews", token,
                """
                {"reviewType":"weekly","moduleCode":"work","title":"API review","summary":"contract review","highlights":"stable","problems":"none","nextActions":"continue","periodStart":"2026-07-08","periodEnd":"%s"}
                """.formatted(FIXED_DATE));
        mockMvc.perform(get("/api/reviews")
                        .queryParam("reviewType", "weekly")
                        .queryParam("moduleCode", "work")
                        .queryParam("periodStart", "2026-07-01")
                        .queryParam("periodEnd", FIXED_DATE)
                        .header(HttpHeaders.AUTHORIZATION, bearer(token)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data", hasSize(1)))
                .andExpect(jsonPath("$.data[0].id").value(reviewId));
        mockMvc.perform(put("/api/reviews/{id}", reviewId)
                        .header(HttpHeaders.AUTHORIZATION, bearer(token))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"reviewType":"monthly","moduleCode":"learning","title":"Updated API review","summary":"updated","highlights":"stable","problems":"none","nextActions":"document","periodStart":"2026-07-01","periodEnd":"%s"}
                                """.formatted(FIXED_DATE)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.reviewType").value("monthly"))
                .andExpect(jsonPath("$.data.moduleCode").value("learning"));

        deleteSuccess("/api/reviews/{id}", reviewId, token);
        deleteSuccess("/api/finance/categories/{id}", categoryId, token);
        deleteSuccess("/api/finance/accounts/{id}", accountId, token);
        deleteSuccess("/api/finance/transactions/{id}", transactionId, token);
        deleteSuccess("/api/tasks/{id}", taskId, token);
        deleteSuccess("/api/records/{id}", recordId, token);
        deleteSuccess("/api/tags/{id}", tagId, token);
    }

    private long postAndReadId(String path, String token, String json) throws Exception {
        var result = mockMvc.perform(post(path)
                        .header(HttpHeaders.AUTHORIZATION, bearer(token))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value("SUCCESS"))
                .andExpect(jsonPath("$.data.id").isNumber())
                .andReturn();

        return objectMapper.readTree(result.getResponse().getContentAsString())
                .path("data")
                .path("id")
                .asLong();
    }

    private void deleteSuccess(String path, long id, String token) throws Exception {
        mockMvc.perform(delete(path, id)
                        .header(HttpHeaders.AUTHORIZATION, bearer(token)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value("SUCCESS"));
    }

    private String loginToken() throws Exception {
        var result = mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"admin\",\"password\":\"matrix-prp\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value("SUCCESS"))
                .andExpect(jsonPath("$.data.token", not(emptyOrNullString())))
                .andReturn();

        return objectMapper.readTree(result.getResponse().getContentAsString())
                .path("data")
                .path("token")
                .asText();
    }

    private String bearer(String token) {
        return "Bearer " + token;
    }
}
