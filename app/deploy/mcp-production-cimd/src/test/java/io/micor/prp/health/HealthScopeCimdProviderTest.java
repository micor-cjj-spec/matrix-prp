package io.micor.prp.health;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import org.keycloak.models.*;
import org.keycloak.representations.idm.ClientRepresentation;
class HealthScopeCimdProviderTest {
 HealthScopeCimdProvider provider(String realm){
  KeycloakSession s=mock(KeycloakSession.class);KeycloakContext c=mock(KeycloakContext.class);RealmModel r=mock(RealmModel.class);
  when(s.getContext()).thenReturn(c);when(c.getRealm()).thenReturn(r);when(r.getName()).thenReturn(realm);return new HealthScopeCimdProvider(s);
 }
 ClientRepresentation client(){var c=new ClientRepresentation();c.setClientId("https://chatgpt.com/oauth/client.json");c.setPublicClient(false);c.setClientAuthenticatorType("client-jwt");c.setAttributes(new HashMap<>());return c;}
 void contract(ClientRepresentation c){
  assertEquals(List.of("basic"),c.getDefaultClientScopes());assertEquals(6,c.getOptionalClientScopes().size());
  assertEquals(Set.of("prp.wellness.read","prp.wellness.write.create","prp.wellness.write.update","prp.wellness.write.delete","prp.wellness.write.status","prp.wellness.write.confirm"),new HashSet<>(c.getOptionalClientScopes()));
  assertTrue(c.isConsentRequired());assertFalse(c.isFullScopeAllowed());assertFalse(c.isDirectAccessGrantsEnabled());assertFalse(c.isServiceAccountsEnabled());assertEquals("S256",c.getAttributes().get("pkce.code.challenge.method"));assertEquals("client-jwt",c.getClientAuthenticatorType());
 }
 @Test void nativeCreationGetsCapabilitiesNotDefaultWriteGrants(){var c=client();provider("prp-mcp-prod").augmentClientMetadata(c);contract(c);}
 @Test void refreshCannotAddOfflineOrTaskScopes(){var c=client();c.setDefaultClientScopes(List.of("offline_access","prp.wellness.write.create"));c.setOptionalClientScopes(List.of("prp.tasks.read"));provider("prp-mcp-prod").augmentClientMetadata(c);contract(c);}
 @Test void repeatedRefreshIsIdempotent(){var c=client();var p=provider("prp-mcp-prod");p.augmentClientMetadata(c);p.augmentClientMetadata(c);contract(c);}
 @Test void unrelatedRealmAndClientAreRefused(){var c=client();assertThrows(IllegalStateException.class,()->provider("prp-mcp").augmentClientMetadata(c));c.setClientId("https://evil.example/client.json");assertThrows(IllegalStateException.class,()->provider("prp-mcp-prod").augmentClientMetadata(c));}
 @Test void authenticationDowngradeIsRefused(){for(String method:List.of("none","client-secret")){var c=client();c.setClientAuthenticatorType(method);assertThrows(IllegalStateException.class,()->provider("prp-mcp-prod").augmentClientMetadata(c));}var c=client();c.setPublicClient(true);assertThrows(IllegalStateException.class,()->provider("prp-mcp-prod").augmentClientMetadata(c));}
 @Test void preservesReviewedRefreshAndJwksSettings(){var c=client();c.getAttributes().put("use.refresh.tokens","true");c.getAttributes().put("jwks.url","https://chatgpt.com/oauth/jwks.json");provider("prp-mcp-prod").augmentClientMetadata(c);assertEquals("true",c.getAttributes().get("use.refresh.tokens"));assertEquals("https://chatgpt.com/oauth/jwks.json",c.getAttributes().get("jwks.url"));}
 @Test void actualNormalizerRegressionCases() throws Exception {MetadataRulesTest.main(new String[0]);}
}
