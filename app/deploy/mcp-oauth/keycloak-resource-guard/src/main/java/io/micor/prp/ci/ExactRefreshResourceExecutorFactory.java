package io.micor.prp.ci;

import java.util.Collections;
import java.util.List;
import org.keycloak.Config.Scope;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.KeycloakSessionFactory;
import org.keycloak.provider.ProviderConfigProperty;
import org.keycloak.representations.idm.ClientPolicyExecutorConfigurationRepresentation;
import org.keycloak.services.clientpolicy.ClientPolicyContext;
import org.keycloak.services.clientpolicy.ClientPolicyException;
import org.keycloak.services.clientpolicy.context.TokenRefreshContext;
import org.keycloak.services.clientpolicy.executor.ClientPolicyExecutorProvider;
import org.keycloak.services.clientpolicy.executor.ClientPolicyExecutorProviderFactory;

/**
 * Ephemeral CI proof-of-concept. NOT approved for any persistent Keycloak realm.
 * Exercises the real client-policy token-refresh event, not a proxy workaround.
 * The synthetic client and resource are deliberately constant and do not target
 * the live PRP, ChatGPT or any user-account credential.
 */
public final class ExactRefreshResourceExecutorFactory implements ClientPolicyExecutorProviderFactory {
    public static final String ID = "prp-ci-refresh-resource-guard";
    private static final String TEST_CLIENT = "ci-authcode-private-jwt";
    private static final String TEST_RESOURCE = "https://prp.staging.example.org/api/mcp";

    @Override
    public String getId() {
        return ID;
    }

    @Override
    public String getHelpText() {
        return "Disposable CI only: reject unexpected OAuth refresh resource for one synthetic client";
    }

    @Override
    public List<ProviderConfigProperty> getConfigProperties() {
        return Collections.emptyList();
    }

    @Override
    public ClientPolicyExecutorProvider create(KeycloakSession session) {
        return new ExactRefreshResourceExecutor();
    }

    @Override
    public void init(Scope config) { }

    @Override
    public void postInit(KeycloakSessionFactory factory) { }

    @Override
    public void close() { }

    private static final class ExactRefreshResourceExecutor
            implements ClientPolicyExecutorProvider<ClientPolicyExecutorConfigurationRepresentation> {
        @Override
        public String getProviderId() {
            return ID;
        }

        @Override
        public void executeOnEvent(ClientPolicyContext context) throws ClientPolicyException {
            if (!(context instanceof TokenRefreshContext refresh)) {
                return;
            }
            if (refresh.getClient() == null
                    || !TEST_CLIENT.equals(refresh.getClient().getClientId())) {
                return;
            }
            List<String> requested = refresh.getParams() == null
                    ? null : refresh.getParams().get("resource");
            // An omitted resource follows the original grant; this prototype
            // guards only explicit new resource requests on refresh.
            if (requested != null && !requested.isEmpty()
                    && (requested.size() != 1 || !TEST_RESOURCE.equals(requested.get(0)))) {
                throw new ClientPolicyException("invalid_target", "Unapproved refresh resource");
            }
        }
    }
}
