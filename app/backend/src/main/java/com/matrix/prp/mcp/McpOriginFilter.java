package com.matrix.prp.mcp;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Reject browser requests from origins that have not been explicitly trusted
 * by the PRP operator. No wildcard, prefix or suffix matching.
 * Non-browser native MCP clients omit Origin; JWT/OAuth authentication still
 * applies to those requests separately.
 */
@Component
@ConditionalOnProperty(prefix = "matrix-prp.mcp", name = "enabled", havingValue = "true")
public class McpOriginFilter extends OncePerRequestFilter {
    private final Set<String> allowedOrigins;

    public McpOriginFilter(
        @Value("${matrix-prp.mcp.allowed-origins:https://micor.top}") String allowed) {
        allowedOrigins = Arrays.stream(allowed.split(",", -1))
            .map(String::trim).filter(value -> !value.isEmpty())
            .collect(Collectors.toUnmodifiableSet());
        if (allowedOrigins.stream().anyMatch(value -> !value.startsWith("https://")
                || value.contains("*") || value.contains("/") && value.substring(8).contains("/"))) {
            throw new IllegalStateException("Invalid MCP origin configuration");
        }
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getServletPath();
        return !("/api/mcp".equals(path) || path.startsWith("/api/mcp/"));
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String origin = request.getHeader(HttpHeaders.ORIGIN);
        if (origin != null && !allowedOrigins.contains(origin)) {
            response.sendError(HttpServletResponse.SC_FORBIDDEN, "MCP origin is not allowed");
            return;
        }
        chain.doFilter(request, response);
    }
}
