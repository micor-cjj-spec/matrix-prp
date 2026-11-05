package io.micor.prp.health;
import java.util.List;
import org.keycloak.models.KeycloakSession;
import org.keycloak.protocol.oidc.*;
import org.keycloak.protocol.oidc.representations.OIDCConfigurationRepresentation;
import org.keycloak.wellknown.WellKnownProvider;

/** Only the production health Realm, not master or any existing test Realm. */
public class HealthDiscoveryFactory extends OIDCWellKnownProviderFactory {
    public String getId(){return "prp-production-health-discovery";}
    public String getAlias(){return "openid-configuration";}
    public int getPriority(){return 1;}
    public WellKnownProvider create(KeycloakSession s){return new OIDCWellKnownProvider(s,null,true){
        public Object getConfig(){
            var c=(OIDCConfigurationRepresentation)super.getConfig();
            if(HealthPolicyFactory.REALM.equals(s.getContext().getRealm().getName())) {
                c.setScopesSupported(HealthPolicyFactory.SCOPES.stream().sorted().toList());
                c.setTokenEndpointAuthMethodsSupported(List.of("private_key_jwt","none"));
                c.setCodeChallengeMethodsSupported(List.of("S256"));
                c.setGrantTypesSupported(List.of("authorization_code","refresh_token"));
                c.setResponseTypesSupported(List.of("code"));
                c.setRegistrationEndpoint(null);
            }
            return c;
        }
    };}
}
