package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
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
class FinanceLedgerDatabaseIT {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;

    private MockHttpServletRequestBuilder authorized(MockHttpServletRequestBuilder req,String token) {
        return req.header(HttpHeaders.AUTHORIZATION,"Bearer "+token);
    }
    private JsonNode postData(String url,String token,Object payload) throws Exception {
        var req=post(url).contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsBytes(payload));
        if(token!=null) req=authorized(req,token);
        return mapper.readTree(mvc.perform(req).andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString()).path("data");
    }
    private JsonNode readData(String url,String token) throws Exception {
        return mapper.readTree(mvc.perform(authorized(get(url),token))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString()).path("data");
    }
    private String login(String user,String password) throws Exception {
        return postData("/api/auth/login",null,Map.of("username",user,"password",password))
                .path("token").asText();
    }
    private JsonNode findBalance(JsonNode balances,long accountId) {
        for(JsonNode balance:balances) if(balance.path("accountId").asLong()==accountId) return balance;
        throw new AssertionError("Account missing: "+accountId);
    }

    @Test
    void openingBalanceTransfersIdempotencyRenameAndIsolation() throws Exception {
        String admin=login("video_admin","video-test-admin-password-2026");
        mvc.perform(get("/api/finance/accounts/balances")).andExpect(status().isUnauthorized());
        long from=postData("/api/finance/accounts",admin,Map.of(
                "name","ledger-checking","type","bank","currency","CNY",
                "openingBalance",500,"note","test")).path("id").asLong();
        long to=postData("/api/finance/accounts",admin,Map.of(
                "name","ledger-wallet","type","cash","currency","CNY",
                "openingBalance",10,"note","test")).path("id").asLong();

        postData("/api/finance/transactions",admin,Map.of(
                "type","income","amount",100,"category","salary","account","ledger-checking",
                "transactionDate","2026-10-11"));
        postData("/api/finance/transactions",admin,Map.of(
                "type","expense","amount",25,"category","food","account","ledger-checking",
                "transactionDate","2026-10-11"));
        Map<String,Object> transfer=Map.of("fromAccountId",from,"toAccountId",to,
                "amount",40,"transferDate","2026-10-11",
                "clientRequestId","ledger-ci-idempotency-2026","note","internal");
        JsonNode first=postData("/api/finance/transfers",admin,transfer);
        assertThat(postData("/api/finance/transfers",admin,transfer).path("id").asLong())
                .isEqualTo(first.path("id").asLong());
        assertThat(readData("/api/finance/transfers",admin).size()).isEqualTo(1);
        JsonNode balances=readData("/api/finance/accounts/balances",admin);
        assertThat(findBalance(balances,from).path("currentBalance").decimalValue()).isEqualByComparingTo("535.00");
        assertThat(findBalance(balances,to).path("currentBalance").decimalValue()).isEqualByComparingTo("50.00");
        JsonNode monthly=readData("/api/finance/summary/monthly?month=2026-10",admin);
        assertThat(monthly.path("income").decimalValue()).isEqualByComparingTo("100.00");
        assertThat(monthly.path("expense").decimalValue()).isEqualByComparingTo("25.00");

        mvc.perform(authorized(put("/api/finance/accounts/{id}",from)
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsBytes(Map.of(
                        "name","ledger-checking-renamed","type","bank","currency","CNY",
                        "openingBalance",500,"note","renamed"))),admin))
                .andExpect(status().isOk());
        assertThat(findBalance(readData("/api/finance/accounts/balances",admin),from)
                .path("currentBalance").decimalValue()).isEqualByComparingTo("535.00");
        assertThat(readData("/api/finance/transfers",admin).get(0).path("fromAccount").asText())
                .isEqualTo("ledger-checking-renamed");
        mvc.perform(authorized(delete("/api/finance/accounts/{id}",from),admin))
                .andExpect(status().isConflict());

        String invitation=postData("/api/auth/invitations",admin,Map.of()).path("code").asText();
        String friend=postData("/api/auth/register",null,Map.of(
                "username","ledger_friend_case","password","friend-password-2026",
                "displayName","Ledger friend","invitationCode",invitation)).path("token").asText();
        assertThat(readData("/api/finance/transfers",friend).size()).isZero();
        assertThat(readData("/api/finance/accounts/balances",friend).size()).isZero();
        mvc.perform(authorized(delete("/api/finance/transfers/{id}",first.path("id").asLong()),friend))
                .andExpect(status().isNotFound());
        mvc.perform(authorized(post("/api/finance/transfers").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsBytes(Map.of("fromAccountId",from,"toAccountId",to,
                        "amount",1,"clientRequestId","cross-tenant-request"))),friend))
                .andExpect(status().isNotFound());

        mvc.perform(authorized(delete("/api/finance/transfers/{id}",first.path("id").asLong()),admin))
                .andExpect(status().isOk());
        assertThat(findBalance(readData("/api/finance/accounts/balances",admin),from)
                .path("currentBalance").decimalValue()).isEqualByComparingTo("575.00");
        assertThat(findBalance(readData("/api/finance/accounts/balances",admin),to)
                .path("currentBalance").decimalValue()).isEqualByComparingTo("10.00");
    }
}
