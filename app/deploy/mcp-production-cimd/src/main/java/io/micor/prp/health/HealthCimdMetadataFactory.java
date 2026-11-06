package io.micor.prp.health;
import org.keycloak.models.KeycloakSession;
import org.keycloak.protocol.oauth2.cimd.clientpolicy.executor.*;
import org.keycloak.services.clientpolicy.executor.ClientPolicyExecutorProvider;
public class HealthCimdMetadataFactory extends ClientIdMetadataDocumentExecutorFactory {
 public String getId(){return "prp-health-cimd-metadata";}
 public ClientPolicyExecutorProvider<ClientIdMetadataDocumentExecutor.Configuration> create(KeycloakSession s){return new HealthCimdMetadata(s,providerConfig);}
}
