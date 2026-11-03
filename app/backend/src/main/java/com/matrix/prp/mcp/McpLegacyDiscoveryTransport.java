package com.matrix.prp.mcp;

import io.modelcontextprotocol.server.McpStatelessServerHandler;
import io.modelcontextprotocol.spec.McpSchema;
import io.modelcontextprotocol.spec.McpStatelessServerTransport;
import java.util.List;
import reactor.core.publisher.Mono;

/**
 * SDK 0.18.3 predates server/discover and turns its missing handler into HTTP 500.
 * Return the standard JSON-RPC method-not-found response so a modern client can
 * fall back to initialize. Do not pretend to support the 2026 protocol.
 * The delegate retains all HTTP, origin and authenticated identity handling.
 */
final class McpLegacyDiscoveryTransport implements McpStatelessServerTransport {
    private final McpStatelessServerTransport delegate;

    McpLegacyDiscoveryTransport(McpStatelessServerTransport delegate) {
        this.delegate = delegate;
    }

    @Override
    public void setMcpHandler(McpStatelessServerHandler handler) {
        delegate.setMcpHandler(new McpStatelessServerHandler() {
            @Override
            public Mono<McpSchema.JSONRPCResponse> handleRequest(
                    io.modelcontextprotocol.common.McpTransportContext context,
                    McpSchema.JSONRPCRequest request) {
                if ("server/discover".equals(request.method())) {
                    return Mono.just(new McpSchema.JSONRPCResponse("2.0", request.id(), null,
                        new McpSchema.JSONRPCResponse.JSONRPCError(-32601, "Method not found", null)));
                }
                return handler.handleRequest(context, request);
            }

            @Override
            public Mono<Void> handleNotification(
                    io.modelcontextprotocol.common.McpTransportContext context,
                    McpSchema.JSONRPCNotification notification) {
                return handler.handleNotification(context, notification);
            }
        });
    }

    @Override
    public List<String> protocolVersions() {
        return delegate.protocolVersions();
    }

    @Override
    public Mono<Void> closeGracefully() {
        return delegate.closeGracefully();
    }
}
