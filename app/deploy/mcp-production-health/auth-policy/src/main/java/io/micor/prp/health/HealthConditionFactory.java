package io.micor.prp.health;
import java.util.List;
import org.keycloak.models.*;
import org.keycloak.provider.ProviderConfigProperty;
import org.keycloak.representations.idm.ClientPolicyConditionConfigurationRepresentation;
import org.keycloak.services.clientpolicy.*;
import org.keycloak.services.clientpolicy.condition.*;
import org.keycloak.services.clientpolicy.context.*;

/** Exact registered ID plus explicit DCR denial, in only the new production Realm. */
public final class HealthConditionFactory extends AbstractClientPolicyConditionProviderFactory {
    public String getId(){return "prp-production-health-client";}
    public String getHelpText(){return "Only the exact production ChatGPT ID; no any-client or URI wildcard";}
    public List<ProviderConfigProperty> getConfigProperties(){return List.of();}
    public ClientPolicyConditionProvider create(KeycloakSession session){return new ClientPolicyConditionProvider<ClientPolicyConditionConfigurationRepresentation>(){
        public void setupConfiguration(ClientPolicyConditionConfigurationRepresentation c){}
        public Class<ClientPolicyConditionConfigurationRepresentation> getConditionConfigurationClass(){return ClientPolicyConditionConfigurationRepresentation.class;}
        public boolean isNegativeLogic(){return false;}
        public String getProviderId(){return "prp-production-health-client";}
        public ClientPolicyVote applyPolicy(ClientPolicyContext context){
            if(session.getContext().getRealm()==null || !HealthPolicyFactory.REALM.equals(session.getContext().getRealm().getName()))return ClientPolicyVote.NO;
            String path=session.getContext().getUri().getRequestUri().getPath();
            if(path.startsWith("/realms/"+HealthPolicyFactory.REALM+"/clients-registrations/"))return ClientPolicyVote.YES;
            String client=null;
            if(context instanceof PreAuthorizationRequestContext a)client=a.getClientId();
            else if(context instanceof PreTokenRequestContext t && t.getClient()!=null)client=t.getClient().getClientId();
            else if(context instanceof TokenRefreshContext t && t.getClient()!=null)client=t.getClient().getClientId();
            else if(session.getContext().getClient()!=null)client=session.getContext().getClient().getClientId();
            return HealthPolicyFactory.CLIENT.equals(client)?ClientPolicyVote.YES:ClientPolicyVote.NO;
        }
    };}
}
