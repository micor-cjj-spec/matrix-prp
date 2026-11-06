package io.micor.prp.health;
import java.util.List;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.ClientModel;
import org.keycloak.protocol.oauth2.cimd.clientpolicy.executor.AbstractClientIdMetadataDocumentExecutor;
import org.keycloak.representations.idm.ClientRepresentation;
import org.keycloak.protocol.oauth2.cimd.provider.PersistentClientIdMetadataDocumentProvider;
/** Candidate: AS-owned capabilities, never user consent or token scope grants. */
public final class HealthScopeCimdProvider extends PersistentClientIdMetadataDocumentProvider {
 public HealthScopeCimdProvider(KeycloakSession session){super(session);}
 @Override public AbstractClientIdMetadataDocumentExecutor.FetchOperation determineFetchOperation(String id){
  if(!"prp-mcp-prod".equals(session.getContext().getRealm().getName()) || !"https://chatgpt.com/oauth/client.json".equals(id))throw new IllegalStateException("UNREVIEWED_CLIENT");
  ClientModel existing=session.getContext().getRealm().getClientByClientId(id);
  if(existing!=null && existing.getAttribute(CIMD_CACHE_EXPIRY_TIME_IN_SEC)==null){
   if(existing.isPublicClient() || existing.isImplicitFlowEnabled() || !"S256".equals(existing.getAttribute("pkce.code.challenge.method")) || !"true".equals(existing.getAttribute("use.jwks.url")) || !"https://chatgpt.com/oauth/jwks.json".equals(existing.getAttribute("jwks.url")) || !"client-jwt".equals(existing.getClientAuthenticatorType()) || !existing.isStandardFlowEnabled() || existing.isDirectAccessGrantsEnabled() || existing.isServiceAccountsEnabled() || existing.isFullScopeAllowed() || !java.util.Set.of("https://chatgpt.com/connector_platform_oauth_redirect").equals(existing.getRedirectUris()))throw new IllegalStateException("UNREVIEWED_EXISTING_CLIENT");
   // Native UPDATE preserves the client UUID and its user consent references.
   // It must still fetch and validate the exact signed-client metadata.
   return AbstractClientIdMetadataDocumentExecutor.FetchOperation.UPDATE;
  }
  return super.determineFetchOperation(id);
 }
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
