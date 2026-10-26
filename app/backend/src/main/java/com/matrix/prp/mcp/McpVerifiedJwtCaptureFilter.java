package com.matrix.prp.mcp;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.filter.OncePerRequestFilter;

/** Only the dedicated OAuth link chain installs this after Bearer signature verification. */
final class McpVerifiedJwtCaptureFilter extends OncePerRequestFilter {
    static final String VERIFIED_JWT = "prp.mcp.verifiedLinkJwt";

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        var auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth instanceof JwtAuthenticationToken jwt && jwt.isAuthenticated()) {
            request.setAttribute(VERIFIED_JWT, jwt);
        }
        chain.doFilter(request, response);
    }
}
