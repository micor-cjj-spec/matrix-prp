package com.matrix.prp.config;

import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.config.MeterFilter;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Set;
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.annotation.Order;
import org.springframework.core.env.Environment;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

/** Opt-in management only; no changes to business JWT, MCP or OAuth filter chains. */
@Configuration(proxyBeanMethods = false)
@Profile("observability")
public class ObservabilityConfig {
    private static final String ROLE = "ROLE_PRP_METRICS";
    private static final Pattern BCRYPT = Pattern.compile("\\$2[aby]\\$(?:12|13|14)\\$[./A-Za-z0-9]{53}");
    private static final Set<String> HTTP_TAGS = Set.of("method", "status", "outcome", "uri", "exception", "error");
    private static final Set<String> JVM_TAGS = Set.of("area", "id", "action", "cause", "state", "gc", "phase", "generation");

    @Bean
    @Order(-10)
    SecurityFilterChain observabilitySecurityChain(
            HttpSecurity http, Environment env,
            @Value("${matrix-prp.observability.password-hash:}") String hash) throws Exception {
        if (!BCRYPT.matcher(hash).matches()) {
            throw new IllegalStateException("Observability requires a dedicated bcrypt password hash (cost 12-14)");
        }
        int configuredPort = env.getProperty("management.server.port", Integer.class, -1);
        int applicationPort = env.getProperty("server.port", Integer.class, 8080);
        if (configuredPort < 0 || (configuredPort != 0 && configuredPort == applicationPort)
                || !"127.0.0.1".equals(env.getProperty("management.server.address"))) {
            throw new IllegalStateException("Observability requires a separate IPv4 loopback management listener");
        }
        // Local provider only. Do not publish a shared UserDetailsService or AuthenticationManager bean.
        var user = User.withUsername("prp-metrics").password(hash).authorities(ROLE).build();
        var provider = new DaoAuthenticationProvider(new InMemoryUserDetailsManager(user));
        provider.setPasswordEncoder(new BCryptPasswordEncoder());
        var actuatorPath = new AntPathRequestMatcher("/actuator/**");
        RequestMatcher managementOnly = request -> actuatorPath.matches(request) || managementPort(request, env);
        var prometheusGet = new AntPathRequestMatcher("/actuator/prometheus", "GET");
        return http.securityMatcher(managementOnly)
                .authenticationManager(new ProviderManager(provider))
                .httpBasic(Customizer.withDefaults())
                .requestCache(cache -> cache.disable())
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(prometheusGet).access((authentication, context) -> {
                            var principal = authentication.get();
                            return new AuthorizationDecision(
                                    managementPort(context.getRequest(), env)
                                    && loopback(context.getRequest().getLocalAddr())
                                    && loopback(context.getRequest().getRemoteAddr())
                                    && principal.isAuthenticated()
                                    && principal.getAuthorities().stream().anyMatch(a -> ROLE.equals(a.getAuthority())));
                        })
                        .anyRequest().denyAll())
                .build();
    }

    private static boolean managementPort(HttpServletRequest request, Environment env) {
        int bound = env.getProperty("local.management.port", Integer.class, -1);
        return bound > 0 && request.getLocalPort() == bound;
    }

    private static boolean loopback(String address) {
        return "127.0.0.1".equals(address) || "::1".equals(address)
                || "0:0:0:0:0:0:0:1".equals(address);
    }

    @Bean
    MeterFilter observabilityMetricAllowlist() {
        return MeterFilter.deny(id -> !allowed(id));
    }

    private static boolean allowed(Meter.Id id) {
        String name = id.getName();
        Set<String> tags;
        if ("http.server.requests".equals(name)) {
            tags = HTTP_TAGS;
        } else if (name.startsWith("jvm.")) {
            tags = JVM_TAGS;
        } else if (name.startsWith("hikaricp.")) {
            tags = Set.of("pool");
        } else if (name.startsWith("process.") || name.startsWith("system.cpu.")
                || name.startsWith("application.")) {
            tags = Set.of("main.application.class");
        } else {
            return false;
        }
        return id.getTags().stream().allMatch(tag -> tags.contains(tag.getKey()));
    }

    @Bean
    MeterFilter observabilityUriBound() {
        return MeterFilter.maximumAllowableTags("http.server.requests", "uri", 256, MeterFilter.deny());
    }

    @Bean
    MeterFilter observabilityMethodBound() {
        return MeterFilter.maximumAllowableTags("http.server.requests", "method", 16, MeterFilter.deny());
    }

    @Bean
    MeterFilter observabilityPoolBound() {
        return MeterFilter.maximumAllowableTags("hikaricp", "pool", 8, MeterFilter.deny());
    }
}
