package io.micor.prp.health;
import org.keycloak.models.KeycloakSession;
import org.keycloak.protocol.oauth2.cimd.provider.*;
public final class HealthScopeCimdProviderFactory extends PersistentClientIdMetadataDocumentProviderFactory {
 public String getId(){return "prp-health-scope-cimd";}
 public HealthScopeCimdProvider create(KeycloakSession session){return new HealthScopeCimdProvider(session);}
}
