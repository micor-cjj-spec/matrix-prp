package io.micor.prp.ci;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.net.URI;
import java.util.List;
import java.util.Objects;
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
 * Candidate SPI for review in disposable Keycloak only; NOT deployed.
 * Fail closed for invalid policy config. Never prints OAuth request data.
 */
public final class ExactRefreshResourceExecutorFactory implements ClientPolicyExecutorProviderFactory {
    public static final String ID = "prp-ci-refresh-resource-guard";
    public static final String TARGET_CLIENT = "target-client-id";
    public static final String EXACT_RESOURCE = "allowed-resource";

    @Override
    public String getId() { return ID; }

    @Override
    public String getHelpText() {
        return "Guard explicit OAuth refresh resource for one exact client (review-only)";
    }

    @Override
    public List<ProviderConfigProperty> getConfigProperties() {
        return List.of(
            new ProviderConfigProperty(TARGET_CLIENT, "Exact OAuth client ID",
                "No wildcards. Applies only to this client; empty values are invalid.",
                ProviderConfigProperty.STRING_TYPE, ""),
            new ProviderConfigProperty(EXACT_RESOURCE, "Exact MCP resource URL",
                "HTTPS protected resource ending /api/mcp. No query, fragment or wildcard.",
                ProviderConfigProperty.STRING_TYPE, "")
        );
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

    public static final class Configuration extends ClientPolicyExecutorConfigurationRepresentation {
        @JsonProperty(TARGET_CLIENT)
        private String targetClientId;
        @JsonProperty(EXACT_RESOURCE)
        private String allowedResource;

        public String getTargetClientId() { return targetClientId; }
        public void setTargetClientId(String value) { targetClientId = value; }
        public String getAllowedResource() { return allowedResource; }
        public void setAllowedResource(String value) { allowedResource = value; }

        @Override
        public boolean validateConfig() { return valid(this); }
    }

    static boolean valid(Configuration cfg) {
        if (cfg == null || cfg.getTargetClientId() == null || cfg.getAllowedResource() == null) {
            return false;
        }
        String client = cfg.getTargetClientId();
        String resource = cfg.getAllowedResource();
        if (client.isBlank() || client.length() > 512
                || !client.equals(client.trim()) || client.contains("*")
                || resource.length() > 2048 || !resource.equals(resource.trim())) {
            return false;
        }
        try {
            URI uri = URI.create(resource);
            return "https".equals(uri.getScheme())
                && uri.getHost() != null && uri.getHost().equals(uri.getHost().toLowerCase())
                && uri.getUserInfo() == null && uri.getQuery() == null && uri.getFragment() == null
                && uri.getPort() == -1 && "/api/mcp".equals(uri.getPath())
                && uri.toASCIIString().equals(resource) && !resource.contains("*");
        } catch (RuntimeException invalid) {
            return false;
        }
    }

    public static final class ExactRefreshResourceExecutor
            implements ClientPolicyExecutorProvider<Configuration> {
        private Configuration configuration;

        @Override
        public String getProviderId() { return ID; }

        @Override
        public void setupConfiguration(Configuration config) { configuration = config; }

        @Override
        public Class<Configuration> getExecutorConfigurationClass() { return Configuration.class; }

        @Override
        public void executeOnEvent(ClientPolicyContext context) throws ClientPolicyException {
            if (!(context instanceof TokenRefreshContext refresh)) { return; }
            // A misconfigured any-client policy must fail closed, not silently
            // grant unchecked refreshes or take over other event types.
            if (!valid(configuration)) {
                throw new ClientPolicyException("invalid_request", "Refresh policy configuration unavailable");
            }
            if (refresh.getClient() == null) {
                throw new ClientPolicyException("invalid_client", "Refresh client unavailable");
            }
            if (!configuration.getTargetClientId().equals(refresh.getClient().getClientId())) {
                return;
            }
            List<String> resources = refresh.getParams() == null
                ? null : refresh.getParams().get("resource");
            // Require explicit canonical resource: don't depend on undocumented
            // implicit-refresh behavior or the caller's SDK version.
            if (resources == null || resources.size() != 1
                    || !Objects.equals(configuration.getAllowedResource(), resources.get(0))) {
                throw new ClientPolicyException("invalid_target", "Refresh resource not permitted");
            }
        }
    }
}
