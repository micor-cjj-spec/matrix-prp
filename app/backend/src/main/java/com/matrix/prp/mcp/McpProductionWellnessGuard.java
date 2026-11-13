package com.matrix.prp.mcp;

import java.net.URI;
import java.util.Set;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/** Explicit opt-in production contract. Never grants permission or performs deployment. */
@Component
@ConditionalOnProperty(prefix="matrix-prp.mcp",name="production-wellness-only",havingValue="true")
public class McpProductionWellnessGuard {
    static final Set<String> SCOPES=Set.of("prp.wellness.read","prp.wellness.write.create",
        "prp.wellness.write.update","prp.wellness.write.delete","prp.wellness.write.status","prp.wellness.write.confirm");
    public McpProductionWellnessGuard(
            @Value("${matrix-prp.mcp.enabled:false}") boolean enabled,
            @Value("${matrix-prp.mcp.oauth.enabled:false}") boolean oauth,
            @Value("${matrix-prp.mcp.write-enabled:false}") boolean write,
            @Value("${spring.flyway.enabled:false}") boolean flyway,
            @Value("${matrix-prp.mcp.production-tasks-only:false}") boolean tasksOnly,
            @Value("${matrix-prp.mcp.oauth.advertised-scopes:}") String scopes,
            @Value("${spring.datasource.url:}") String jdbc,
            @Value("${matrix-prp.mcp.oauth.resource:}") String resource,
            @Value("${matrix-prp.mcp.oauth.issuer:}") String issuer,
            @Value("${matrix-prp.mcp.expanded-user-ids:}") String owners) {
        verify(enabled,oauth,write,flyway,tasksOnly,scopes,jdbc,resource,issuer,owners);
    }
    static void verify(boolean enabled,boolean oauth,boolean write,boolean flyway,boolean tasksOnly,
                       String scopes,String jdbc,String resource,String issuer,String owners) {
        boolean db=false;
        try {
            if(jdbc!=null && jdbc.startsWith("jdbc:mysql://")) {
                URI u=URI.create(jdbc.substring(5));
                db=Set.of("127.0.0.1","localhost","[::1]").contains(u.getHost())
                    && "/matrix_prp".equals(u.getRawPath()) && u.getUserInfo()==null && u.getFragment()==null
                    && (u.getPort()==-1 || u.getPort()==3306);
                // Apply the already-reviewed production JDBC option boundary too.
                if(db) McpProductionTaskOnlyGuard.verify(true,true,false,"prp.tasks.read",jdbc,false,java.util.List.of());
            }
        } catch(RuntimeException e) { db=false; }
        var selected=McpOAuthMetadataController.parseAdvertisedScopes(scopes,write);
        if(!enabled || !oauth || !write || flyway || tasksOnly || !db || !SCOPES.equals(Set.copyOf(selected))
                || !"https://micor.top/api/mcp".equals(resource)
                || !"https://auth.micor.top/realms/prp-mcp-prod".equals(issuer)
                || owners==null || !owners.matches("[1-9][0-9]*(,[1-9][0-9]*)*"))
            throw new IllegalStateException("Production health-only MCP configuration rejected");
    }
}
