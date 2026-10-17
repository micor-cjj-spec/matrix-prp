package com.matrix.prp.activity;
import com.matrix.prp.auth.model.UserProfile;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.HandlerMapping;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
/** Authenticated MVC request duration, including completion of asynchronous SSE. */
@Configuration
public class ActivityLogMvcConfig implements WebMvcConfigurer {
    private static final Logger LOG=LoggerFactory.getLogger(ActivityLogMvcConfig.class);
    private static final String START=ActivityLogMvcConfig.class.getName()+".start";
    private static final String OWNER=ActivityLogMvcConfig.class.getName()+".owner";
    private final ActivityLogStore logs;
    public ActivityLogMvcConfig(ActivityLogStore logs) { this.logs=logs; }
    @Override public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new HandlerInterceptor() {
            @Override public boolean preHandle(HttpServletRequest request,HttpServletResponse response,Object handler) {
                if(request.getAttribute(START)==null) {
                    var auth=SecurityContextHolder.getContext().getAuthentication();
                    if(auth!=null && auth.isAuthenticated() && auth.getPrincipal() instanceof UserProfile user) {
                        request.setAttribute(START,System.nanoTime());
                        request.setAttribute(OWNER,user.id());
                    }
                }
                return true;
            }
            @Override public void afterCompletion(HttpServletRequest request,HttpServletResponse response,
                                                   Object handler,Exception error) {
                Object start=request.getAttribute(START),owner=request.getAttribute(OWNER);
                if(!(start instanceof Long started) || !(owner instanceof Long userId)) return;
                Object template=request.getAttribute(HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
                if(!(template instanceof String route) || !route.startsWith("/api/")) return;
                long elapsed=(System.nanoTime()-started)/1_000_000;
                try { logs.recordHttp(userId,request.getMethod(),route,response.getStatus(),elapsed); }
                catch(RuntimeException ex) { LOG.warn("Structured activity audit write unavailable"); }
            }
        }).addPathPatterns("/api/**").excludePathPatterns("/api/health","/api/health/**",
                            "/api/auth/**","/api/video/media/**");
    }
}
