package com.matrix.prp;

import static org.hamcrest.Matchers.greaterThan;
import static org.hamcrest.Matchers.emptyOrNullString;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

@ActiveProfiles("test")
@AutoConfigureMockMvc
@SpringBootTest
@TestPropertySource(properties = "matrix-prp.knowledge.root=src/test/resources/knowledge")
class ApiContractTests {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Test
    void loginAndCurrentUserUseUnifiedResponseEnvelope() throws Exception {
        String token = loginToken();

        mockMvc.perform(get("/api/users/me")
                        .header(HttpHeaders.AUTHORIZATION, bearer(token)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value("SUCCESS"))
                .andExpect(jsonPath("$.message").value("OK"))
                .andExpect(jsonPath("$.data.username").value("admin"))
                .andExpect(jsonPath("$.data.displayName").value("Matrix PRP"));
    }

    @Test
    void dashboardSummaryUsesStableContractForClients() throws Exception {
        String token = loginToken();

        mockMvc.perform(get("/api/dashboard/summary")
                        .header(HttpHeaders.AUTHORIZATION, bearer(token)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value("SUCCESS"))
                .andExpect(jsonPath("$.data.date").exists())
                .andExpect(jsonPath("$.data.todayTaskCount").isNumber())
                .andExpect(jsonPath("$.data.overdueTaskCount").isNumber())
                .andExpect(jsonPath("$.data.monthlyBalance").isNumber())
                .andExpect(jsonPath("$.data.todayTasks").isArray())
                .andExpect(jsonPath("$.data.highPriorityTasks").isArray())
                .andExpect(jsonPath("$.data.recentRecords").isArray())
                .andExpect(jsonPath("$.data.modules").isArray());
    }

    @Test
    void knowledgeApisUseStableContractAndRejectUnsafePaths() throws Exception {
        String token = loginToken();

        mockMvc.perform(get("/api/knowledge/tree")
                        .header(HttpHeaders.AUTHORIZATION, bearer(token)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value("SUCCESS"))
                .andExpect(jsonPath("$.data[0].name").value("api-contract.md"))
                .andExpect(jsonPath("$.data[0].type").value("file"));

        mockMvc.perform(get("/api/knowledge/stats")
                        .header(HttpHeaders.AUTHORIZATION, bearer(token)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value("SUCCESS"))
                .andExpect(jsonPath("$.data.fileCount").value(1))
                .andExpect(jsonPath("$.data.directoryCount").value(0))
                .andExpect(jsonPath("$.data.totalBytes").value(greaterThan(0)));

        mockMvc.perform(get("/api/knowledge/files")
                        .queryParam("path", "api-contract.md")
                        .header(HttpHeaders.AUTHORIZATION, bearer(token)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value("SUCCESS"))
                .andExpect(jsonPath("$.data.path").value("api-contract.md"))
                .andExpect(jsonPath("$.data.content").value(org.hamcrest.Matchers.containsString("contract search marker")));

        mockMvc.perform(get("/api/knowledge/search")
                        .queryParam("q", "contract")
                        .header(HttpHeaders.AUTHORIZATION, bearer(token)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value("SUCCESS"))
                .andExpect(jsonPath("$.data[0].path").value("api-contract.md"))
                .andExpect(jsonPath("$.data[0].score").value(greaterThan(0)));

        mockMvc.perform(get("/api/knowledge/files")
                        .queryParam("path", "../pom.xml")
                        .header(HttpHeaders.AUTHORIZATION, bearer(token)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"));
    }

    private String loginToken() throws Exception {
        var result = mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"admin\",\"password\":\"matrix-prp\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value("SUCCESS"))
                .andExpect(jsonPath("$.data.token", not(emptyOrNullString())))
                .andExpect(jsonPath("$.data.tokenType").value("Bearer"))
                .andExpect(jsonPath("$.data.user.username").value("admin"))
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
