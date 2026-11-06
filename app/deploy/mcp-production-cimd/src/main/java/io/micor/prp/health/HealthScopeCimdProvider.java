package io.micor.prp.health;
import java.util.List;
import org.keycloak.models.KeycloakSession;
import org.keycloak.representations.idm.ClientRepresentation;
import org.keycloak.protocol.oauth2.cimd.provider.PersistentClientIdMetadataDocumentProvider;
/** Candidate: AS-owned capabilities, never user consent or token scope grants. */
public final class HealthScopeCimdProvider extends PersistentClientIdMetadataDocumentProvider {
 public HealthScopeCimdProvider(KeycloakSession session){super(session);}
 @Override public void augmentClientMetadata(ClientRepresentation rep){
  if(!"prp-mcp-prod".equals(session.getContext().getRealm().getName()) || !"https://chatgpt.com/oauth/client.json".equals(rep.getClientId()))throw new IllegalStateException("UNREVIEWED_CLIENT");
  super.augmentClientMetadata(rep);
  if(Boolean.TRUE.equals(rep.isPublicClient()) || !"client-jwt".equals(rep.getClientAuthenticatorType()))throw new IllegalStateException("CLIENT_AUTHENTICATION");
  rep.setDefaultClientScopes(List.of("basic"));
  rep.setOptionalClientScopes(List.of("prp.wellness.read","prp.wellness.write.create","prp.wellness.write.update","prp.wellness.write.delete","prp.wellness.write.status","prp.wellness.write.confirm"));
  rep.setDirectAccessGrantsEnabled(false);rep.setServiceAccountsEnabled(false);
  rep.getAttributes().put("pkce.code.challenge.method","S256");
  rep.getAttributes().put("token.endpoint.auth.signing.alg","RS256");
 }
}
