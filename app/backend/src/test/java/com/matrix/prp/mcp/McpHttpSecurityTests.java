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
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.jdbc.core.JdbcTemplate;
import com.matrix.prp.wellness.WellnessService;
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
    // The standard test profile intentionally has no real JDBC datasource.
    @MockitoBean JdbcTemplate db;
    @MockitoBean WellnessService wellness;
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
    void rejectsForeignBrowserOriginsButPermitsTrustedOriginToReachJwtGate() throws Exception {
        mvc.perform(post("/api/mcp")
            .header(HttpHeaders.ORIGIN, "https://attacker.example")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\"}"))
            .andExpect(status().isForbidden());
        String id = "41abc027-d67e-4bdf-8985-e3ec97d23204";
        mvc.perform(post("/api/mcp/approval/drafts/{id}/approve", id)
            .header(HttpHeaders.ORIGIN, "https://micor.top.attacker.example")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"password\":\"not-the-password\"}"))
            .andExpect(status().isForbidden());
        mvc.perform(post("/api/mcp")
            .with(request -> {
                request.setScheme("https");
                request.setServerName("micor.top");
                request.setServerPort(443);
                request.setSecure(true);
                return request;
            })
            .header(HttpHeaders.ORIGIN, "https://micor.top")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/list\"}"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedTransportListsOnlyExplicitMcpTools() throws Exception {
        String loginResponse = mvc.perform(post("/api/auth/login")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {"username":"admin","password":"matrix-prp"}
                """))
            .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        String token = json.readTree(loginResponse).path("data").path("token").asText();
        var initialization = mvc.perform(post("/api/mcp")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON, MediaType.TEXT_EVENT_STREAM)
            .content("""
                {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"prp-mcp-test","version":"1.0"}}}
                """)).andReturn();
        if (initialization.getRequest().isAsyncStarted()) {
            initialization = mvc.perform(asyncDispatch(initialization)).andReturn();
        }
        org.assertj.core.api.Assertions.assertThat(initialization.getResponse().getStatus())
            .as("MCP initialize handler=%s; exception=%s; response=%s", initialization.getHandler(), initialization.getResolvedException(), initialization.getResponse().getContentAsString())
            .isEqualTo(200);
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
        org.assertj.core.api.Assertions.assertThat(result.getResponse().getStatus())
            .as("MCP tools/list response: %s", result.getResponse().getContentAsString()).isEqualTo(200);
        org.assertj.core.api.Assertions.assertThat(result.getResponse().getContentAsString())
            .contains("prp_tasks_list", "prp_prepare_task", "prp_confirm_draft")
            .doesNotContain("exec_sql", "arbitrary_url");
        var call = mvc.perform(post("/api/mcp")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON, MediaType.TEXT_EVENT_STREAM)
            .content("""
                {"jsonrpc":"2.0","id":11,"method":"tools/call","params":{"name":"prp_tasks_list","arguments":{}}}
                """)).andReturn();
        if (call.getRequest().isAsyncStarted()) {
            call = mvc.perform(asyncDispatch(call)).andReturn();
        }
        org.assertj.core.api.Assertions.assertThat(call.getResponse().getStatus()).isEqualTo(200);
        org.assertj.core.api.Assertions.assertThat(call.getResponse().getContentAsString())
            .contains("result").doesNotContain("Authentication required", "\"isError\":true");
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
