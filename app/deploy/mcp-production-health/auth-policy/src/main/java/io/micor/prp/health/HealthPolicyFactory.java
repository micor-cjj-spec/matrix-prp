package io.micor.prp.health;

import java.util.*;
import jakarta.ws.rs.core.MultivaluedMap;
import org.keycloak.Config;
import org.keycloak.models.*;
import org.keycloak.provider.ProviderConfigProperty;
import org.keycloak.representations.idm.ClientPolicyExecutorConfigurationRepresentation;
import org.keycloak.services.clientpolicy.*;
import org.keycloak.services.clientpolicy.context.*;
import org.keycloak.services.clientpolicy.executor.*;

/** Fixed production CANDIDATE: no metadata fetching, registration or authentication bypass. */
public final class HealthPolicyFactory implements ClientPolicyExecutorProviderFactory {
    public static final String ID="prp-production-health-policy";
    static final String REALM="prp-mcp-prod", CLIENT="https://chatgpt.com/oauth/client.json";
    static final String RESOURCE="https://micor.top/api/mcp";
    static final String REDIRECT="https://chatgpt.com/connector_platform_oauth_redirect";
    static final Set<String> SCOPES=Set.of("prp.wellness.read","prp.wellness.write.create",
        "prp.wellness.write.update","prp.wellness.write.delete","prp.wellness.write.status","prp.wellness.write.confirm");
    public String getId(){return ID;}
    public String getHelpText(){return "Exact pre-registered ChatGPT health client only; candidate, not installation approval";}
    public List<ProviderConfigProperty> getConfigProperties(){return List.of();}
    public void init(Config.Scope c){}
    public void postInit(KeycloakSessionFactory f){}
    public void close(){}
    public ClientPolicyExecutorProvider create(KeycloakSession s){return new Executor(s);}
    public static class Settings extends ClientPolicyExecutorConfigurationRepresentation {}
    static ClientPolicyException deny(String category){return new ClientPolicyException("invalid_request","PRP_HEALTH_"+category);}
    static String one(MultivaluedMap<String,String> p,String name,boolean required)throws ClientPolicyException {
        List<String> v=p==null?null:p.get(name);
        if(v==null && !required)return null;
        if(v==null || v.size()!=1 || v.get(0)==null || v.get(0).isBlank())throw deny("PARAMETER");
        return v.get(0);
    }
    static void scopes(String value,boolean required)throws ClientPolicyException {
        if(value==null && !required)return;
        if(value==null || value.length()>512 || value.isBlank())throw deny("SCOPE");
        var found=new HashSet<String>();
        for(String s:value.split(" ",-1))if(!SCOPES.contains(s)||!found.add(s))throw deny("SCOPE");
    }
    static void authorization(MultivaluedMap<String,String> p)throws ClientPolicyException {
        if(!CLIENT.equals(one(p,"client_id",true)) || !REDIRECT.equals(one(p,"redirect_uri",true))
                || !"code".equals(one(p,"response_type",true)) || !RESOURCE.equals(one(p,"resource",true))
                || !"S256".equals(one(p,"code_challenge_method",true))
                || !one(p,"code_challenge",true).matches("[A-Za-z0-9_-]{43}"))throw deny("AUTHORIZATION");
        scopes(one(p,"scope",true),true);
    }
    static void token(MultivaluedMap<String,String> p)throws ClientPolicyException {
        if(!RESOURCE.equals(one(p,"resource",true)))throw deny("RESOURCE");
        scopes(one(p,"scope",false),false);
    }
    public static final class Executor implements ClientPolicyExecutorProvider<Settings> {
        private final KeycloakSession session;
        Executor(KeycloakSession s){session=s;}
        public void setupConfiguration(Settings c){}
        public Class<Settings> getExecutorConfigurationClass(){return Settings.class;}
        public String getProviderId(){return ID;}
        public void executeOnEvent(ClientPolicyContext context)throws ClientPolicyException {
            if(session.getContext().getRealm()==null || !REALM.equals(session.getContext().getRealm().getName()))throw deny("REALM");
            String path=session.getContext().getUri().getRequestUri().getPath();
            if(path.startsWith("/realms/"+REALM+"/clients-registrations/"))throw deny("DCR_DISABLED");
            if(context instanceof PreAuthorizationRequestContext a)authorization(a.getRequestParameters());
            if(context instanceof TokenRequestContext t)token(t.getParams());
            if(context instanceof TokenRefreshContext t)token(t.getParams());
            ClientModel client=session.getContext().getClient();
            if(client!=null && CLIENT.equals(client.getClientId()) &&
                    (client.isPublicClient() || !"client-jwt".equals(client.getClientAuthenticatorType())
                        || client.isDirectAccessGrantsEnabled() || client.isServiceAccountsEnabled()
                        || client.isFullScopeAllowed()))throw deny("CLIENT_SECURITY");
        }
    }
}
