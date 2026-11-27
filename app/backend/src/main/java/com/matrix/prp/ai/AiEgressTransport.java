package com.matrix.prp.ai;

import java.net.InetSocketAddress;
import java.net.ProxySelector;
import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.http.client.reactive.JdkClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

/**
 * Optional, deployment-owned proxy for model traffic only. No user setting,
 * credential, endpoint rewrite, trust override or direct fallback is introduced.
 */
public final class AiEgressTransport {
    private AiEgressTransport() {}

    static InetSocketAddress configuredProxy() {
        return proxyAddress(System.getenv("MATRIX_PRP_AI_EGRESS_PROXY_HOST"),
                            System.getenv("MATRIX_PRP_AI_EGRESS_PROXY_PORT"));
    }

    static InetSocketAddress proxyAddress(String host, String port) {
        if ((host == null || host.isEmpty()) && (port == null || port.isEmpty())) return null;
        if (host == null || host.length() > 253
                || !host.matches("[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?")
                || host.contains("..") || port == null || !port.matches("[1-9][0-9]{0,4}"))
            throw new IllegalArgumentException("Invalid AI egress proxy configuration");
        int number = Integer.parseInt(port);
        if (number > 65535) throw new IllegalArgumentException("Invalid AI egress proxy port");
        return InetSocketAddress.createUnresolved(host, number);
    }

    public static HttpClient.Builder httpClient() {
        return httpClient(configuredProxy());
    }

    static HttpClient.Builder httpClient(InetSocketAddress proxy) {
        HttpClient.Builder builder = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(8))
            .followRedirects(HttpClient.Redirect.NEVER);
        if (proxy != null) builder.proxy(ProxySelector.of(proxy));
        return builder;
    }

    static WebClient.Builder streamingClient() {
        return streamingClient(configuredProxy());
    }

    static WebClient.Builder streamingClient(InetSocketAddress proxy) {
        // Preserve the existing default WebClient transport when disabled.
        WebClient.Builder builder = WebClient.builder();
        if (proxy != null) builder.clientConnector(new JdkClientHttpConnector(httpClient(proxy).build()));
        return builder;
    }
}
