package com.matrix.prp.mcp;

import com.matrix.prp.auth.model.UserProfile;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * This filter is installed ONLY in the dedicated OAuth MCP SecurityFilterChain,
 * directly after BearerTokenAuthenticationFilter verified the external JWT.
 * A servlet request attribute is request-scoped and cannot be supplied by an
 * MCP client's JSON or HTTP headers.
 */
final class McpVerifiedPrincipalCaptureFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth != null && auth.isAuthenticated() && auth.getPrincipal() instanceof UserProfile) {
            request.setAttribute(McpOAuthTransportConfiguration.VERIFIED_AUTH, auth);
        }
        chain.doFilter(request, response);
    }
}
