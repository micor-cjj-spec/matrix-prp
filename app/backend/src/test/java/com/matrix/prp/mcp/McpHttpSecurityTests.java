package com.matrix.prp.mcp;

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
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** Real servlet filter-chain security checks with the opt-in MCP transport registered. */
@SpringBootTest
@AutoConfigureMockMvc(print = org.springframework.boot.test.autoconfigure.web.servlet.MockMvcPrint.NONE)
@ActiveProfiles("test")
@TestPropertySource(properties = {
    "matrix-prp.mcp.enabled=true",
    "matrix-prp.mcp.write-enabled=false",
    "spring.ai.mcp.server.enabled=true",
})
class McpHttpSecurityTests {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;

    @Test
    void anonymousMcpOperationsAndHumanApprovalEndpointsAreUnauthorized() throws Exception {
        mvc.perform(post("/api/mcp")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON, MediaType.TEXT_EVENT_STREAM)
            .content("""
                {"jsonrpc":"2.0","id":1,"method":"tools/list"}
                """)).andExpect(status().isUnauthorized());

        String id = "41abc027-d67e-4bdf-8985-e3ec97d23204";
        mvc.perform(get("/api/mcp/approval/drafts/{id}", id))
            .andExpect(status().isUnauthorized());
        mvc.perform(post("/api/mcp/approval/drafts/{id}/approve", id)
            .contentType(MediaType.APPLICATION_JSON).content("{\"password\":\"any\"}"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedTransportListsOnlyExplicitMcpTools() throws Exception {
        String loginResponse = mvc.perform(post("/api/auth/login")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\\"username\\":\\"admin\\",\\"password\\":\\"matrix-prp\\"}"))
            .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        String token = json.readTree(loginResponse).path("data").path("token").asText();
        var result = mvc.perform(post("/api/mcp")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON, MediaType.TEXT_EVENT_STREAM)
            .content("""
                {"jsonrpc":"2.0","id":10,"method":"tools/list","params":{}}
                """)).andReturn();
        if (result.getRequest().isAsyncStarted()) {
            result = mvc.perform(asyncDispatch(result)).andReturn();
        }
        org.assertj.core.api.Assertions.assertThat(result.getResponse().getStatus()).isEqualTo(200);
        org.assertj.core.api.Assertions.assertThat(result.getResponse().getContentAsString())
            .contains("prp_tasks_list", "prp_prepare_task", "prp_confirm_draft")
            .doesNotContain("exec_sql", "arbitrary_url");
    }

    @Test
    void authenticatedUserCannotApproveWhenWriteSwitchIsOff() throws Exception {
        String body = mvc.perform(post("/api/auth/login")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"username\":\"admin\",\"password\":\"matrix-prp\"}"))
            .andExpect(status().isOk())
            .andReturn().getResponse().getContentAsString();
        String token = json.readTree(body).path("data").path("token").asText();
        mvc.perform(get("/api/mcp/approval/drafts/41abc027-d67e-4bdf-8985-e3ec97d23204")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
            .andExpect(status().isForbidden());
    }
}
