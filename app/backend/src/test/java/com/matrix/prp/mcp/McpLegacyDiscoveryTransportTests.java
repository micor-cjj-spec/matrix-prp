package com.matrix.prp.mcp;

import io.modelcontextprotocol.common.McpTransportContext;
import io.modelcontextprotocol.server.McpStatelessServerHandler;
import io.modelcontextprotocol.spec.McpSchema;
import io.modelcontextprotocol.spec.McpStatelessServerTransport;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import reactor.core.publisher.Mono;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

class McpLegacyDiscoveryTransportTests {
    @Test
    void onlyDiscoveryIsInterceptedAndIdsRetainTheirType() {
        var delegate = mock(McpStatelessServerTransport.class);
        var handler = mock(McpStatelessServerHandler.class);
        var transport = new McpLegacyDiscoveryTransport(delegate);
        transport.setMcpHandler(handler);
        var capture = ArgumentCaptor.forClass(McpStatelessServerHandler.class);
        verify(delegate).setMcpHandler(capture.capture());
        var wrapped = capture.getValue();
        for (Object id : List.of("openai-mcp-discover", 42L)) {
            var request = new McpSchema.JSONRPCRequest("2.0", "server/discover", id, Map.of());
            var response = wrapped.handleRequest(McpTransportContext.EMPTY, request).block();
            assertThat(response.id()).isEqualTo(id);
            assertThat(response.error().code()).isEqualTo(-32601);
            assertThat(response.result()).isNull();
        }
        verifyNoInteractions(handler);
        var request = new McpSchema.JSONRPCRequest("2.0", "tools/list", 7L, Map.of());
        var response = new McpSchema.JSONRPCResponse("2.0", 7L, Map.of("tools", List.of()), null);
        when(handler.handleRequest(McpTransportContext.EMPTY, request)).thenReturn(Mono.just(response));
        assertThat(wrapped.handleRequest(McpTransportContext.EMPTY, request).block()).isSameAs(response);
        var notification = new McpSchema.JSONRPCNotification("2.0", "notifications/initialized", Map.of());
        when(handler.handleNotification(McpTransportContext.EMPTY, notification)).thenReturn(Mono.empty());
        wrapped.handleNotification(McpTransportContext.EMPTY, notification).block();
        verify(handler).handleNotification(McpTransportContext.EMPTY, notification);
    }

    @Test
    void supportedProtocolsAndShutdownRemainOwnedByTheDelegate() {
        var delegate = mock(McpStatelessServerTransport.class);
        when(delegate.protocolVersions()).thenReturn(List.of("2025-06-18"));
        when(delegate.closeGracefully()).thenReturn(Mono.empty());
        var transport = new McpLegacyDiscoveryTransport(delegate);
        assertThat(transport.protocolVersions()).containsExactly("2025-06-18");
        transport.closeGracefully().block();
        verify(delegate).closeGracefully();
    }
}
