package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.ai.AgentTaskStore;
import com.matrix.prp.ai.OpenClawGatewayClient;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

class OpenClawGatewayClientTests {
    private final ObjectMapper json = new ObjectMapper();
    private final String token = "test-only-gateway-token-24-chars";
    private AgentTaskStore.AgentTask task() {
        return new AgentTaskStore.AgentTask("11111111-1111-1111-1111-111111111111",9,"PLAN",
            "Explain the learning schedule","RUNNING",null,null,LocalDateTime.now(),LocalDateTime.now(),
            9L,LocalDateTime.now(),"prp:9:11111111-1111-1111-1111-111111111111");
    }
    @Test void defaultsOffAndRejectsUnsafeConfiguration() {
        assertThat(new OpenClawGatewayClient(json,false,true,token,18790,"prp-planner").configured()).isFalse();
        assertThat(new OpenClawGatewayClient(json,true,false,token,18790,"prp-planner").configured()).isFalse();
        assertThat(new OpenClawGatewayClient(json,true,true,"",18790,"prp-planner").configured()).isFalse();
        assertThat(new OpenClawGatewayClient(json,true,true,token,18790,"../agent").configured()).isFalse();
        assertThat(new OpenClawGatewayClient(json,true,true,token,18790,"prp-planner").configured()).isTrue();
        assertThatThrownBy(() -> new OpenClawGatewayClient(json,false,true,token,18790,"prp-planner")
            .generate(task())).isInstanceOf(Exception.class);
    }
    @Test void sendsApprovedTextToFixedLoopbackWithScopedTaskSession() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        AtomicReference<JsonNode> requestBody = new AtomicReference<>();
        AtomicReference<String> auth = new AtomicReference<>();
        server.createContext("/v1/chat/completions", exchange -> {
            auth.set(exchange.getRequestHeaders().getFirst("Authorization"));
            requestBody.set(json.readTree(exchange.getRequestBody()));
            byte[] bytes = "{\"choices\":[{\"message\":{\"content\":\"Safe written plan\"}}]}"
                .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type","application/json");
            exchange.sendResponseHeaders(200,bytes.length);
            try (var out = exchange.getResponseBody()) { out.write(bytes); }
        });
        server.start();
        try {
            OpenClawGatewayClient client = new OpenClawGatewayClient(json,true,true,token,
                server.getAddress().getPort(),"prp-planner");
            assertThat(client.generate(task())).isEqualTo("Safe written plan");
            assertThat(auth.get()).isEqualTo("Bearer " + token);
            assertThat(requestBody.get().path("model").asText()).isEqualTo("openclaw/prp-planner");
            assertThat(requestBody.get().path("user").asText()).isEqualTo(task().sessionRef());
            assertThat(requestBody.get().path("tool_choice").asText()).isEqualTo("none");
            assertThat(requestBody.get().path("messages").size()).isEqualTo(1);
        } finally { server.stop(0); }
    }
}
