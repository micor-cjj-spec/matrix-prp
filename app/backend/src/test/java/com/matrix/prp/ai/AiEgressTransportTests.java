package com.matrix.prp.ai;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Proxy;
import java.net.ServerSocket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import static org.junit.jupiter.api.Assertions.*;

class AiEgressTransportTests {
    private static final URI DESTINATION = URI.create("https://model.invalid/chat/completions");

    @Test
    void defaultsOffAndPartialOrInvalidConfigurationFailsClosed() {
        assertNull(AiEgressTransport.proxyAddress(null, null));
        assertNull(AiEgressTransport.proxyAddress("", ""));
        assertThrows(IllegalArgumentException.class, () -> AiEgressTransport.proxyAddress("proxy", null));
        assertThrows(IllegalArgumentException.class, () -> AiEgressTransport.proxyAddress(null, "3128"));
        assertThrows(IllegalArgumentException.class, () -> AiEgressTransport.proxyAddress("http://proxy", "3128"));
        assertThrows(IllegalArgumentException.class, () -> AiEgressTransport.proxyAddress("proxy", "65536"));
        assertThrows(IllegalArgumentException.class, () -> AiEgressTransport.proxyAddress("proxy", "0"));
        var address = AiEgressTransport.proxyAddress("prp-model-egress", "3128");
        assertEquals("prp-model-egress", address.getHostString());
        assertEquals(3128, address.getPort());
        var client = AiEgressTransport.httpClient(address).build();
        var routes = client.proxy().orElseThrow().select(DESTINATION);
        assertEquals(1, routes.size());
        assertEquals(Proxy.Type.HTTP, routes.get(0).type());
        assertEquals(address, routes.get(0).address());
        assertEquals(HttpClient.Redirect.NEVER, client.followRedirects());
    }

    // The reserved .invalid target is never contacted: the loopback fake
    // proxy records only CONNECT and refuses it before any TLS or request body.
    @Test @Timeout(15)
    void nativeAndStreamingTransportsUseConnectAndDoNotFallBack() throws Exception {
        for (boolean streaming : new boolean[]{false, true}) {
            try (var server = new ServerSocket(0, 1, InetAddress.getByName("127.0.0.1"));
                 var executor = Executors.newSingleThreadExecutor()) {
                server.setSoTimeout(5000);
                var seen = executor.submit(() -> {
                    try (var socket = server.accept()) {
                        socket.setSoTimeout(3000);
                        var reader = new BufferedReader(new InputStreamReader(socket.getInputStream(), StandardCharsets.US_ASCII));
                        String first = reader.readLine();
                        String line;
                        while ((line = reader.readLine()) != null && !line.isEmpty()) { }
                        socket.getOutputStream().write("HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".getBytes(StandardCharsets.US_ASCII));
                        socket.getOutputStream().flush();
                        return first;
                    }
                });
                var proxy = new InetSocketAddress("127.0.0.1", server.getLocalPort());
                if (streaming) {
                    assertThrows(Exception.class, () -> AiEgressTransport.streamingClient(proxy).build()
                        .get().uri(DESTINATION).retrieve().bodyToMono(String.class).block(Duration.ofSeconds(5)));
                } else {
                    assertThrows(Exception.class, () -> {
                        try (var client = AiEgressTransport.httpClient(proxy).build()) {
                            client.send(HttpRequest.newBuilder(DESTINATION).timeout(Duration.ofSeconds(5)).GET().build(),
                                HttpResponse.BodyHandlers.discarding());
                        }
                    });
                }
                assertEquals("CONNECT model.invalid:443 HTTP/1.1", seen.get(6, TimeUnit.SECONDS));
            }
        }
    }
}
