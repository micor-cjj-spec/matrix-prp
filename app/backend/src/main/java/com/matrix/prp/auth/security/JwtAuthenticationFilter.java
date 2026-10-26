package com.matrix.prp.auth.security;

import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.auth.service.JwtService;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.List;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class JwtAuthenticationFilter extends OncePerRequestFilter {
    private final JwtService jwtService;
    private final UserStore users;
    @Value("${matrix-prp.mcp.oauth.enabled:false}")
    private boolean mcpOAuthEnabled;

    public JwtAuthenticationFilter(JwtService jwtService, UserStore users) {
        this.jwtService = jwtService;
        this.users = users;
    }

    // Never accept first-party PRP JWTs on the OAuth-only MCP transport.
    // This applies even if servlet auto-registration invokes the filter outside
    // the Spring Security filter chain.
    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return mcpOAuthEnabled && ("/api/mcp".equals(request.getServletPath()) || "/api/mcp/link".equals(request.getServletPath()));
    }

    // SSE resumes on a servlet async dispatch. Restore the JWT principal on that dispatch.
    @Override
    protected boolean shouldNotFilterAsyncDispatch() { return false; }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        String authorization = request.getHeader("Authorization");
        if (authorization != null && authorization.startsWith("Bearer ")) {
            try {
                UserProfile claims = jwtService.parseToken(authorization.substring(7));
                UserAccount user = users.findById(claims.id()).orElse(null);
                if (user != null && user.enabled() && user.username().equals(claims.username())) {
                    var authentication = new UsernamePasswordAuthenticationToken(
                            user.profile(), null, List.of(new SimpleGrantedAuthority("ROLE_USER")));
                    SecurityContextHolder.getContext().setAuthentication(authentication);
                }
            } catch (RuntimeException ignored) {
                SecurityContextHolder.clearContext();
            }
        }
        filterChain.doFilter(request, response);
    }
}

