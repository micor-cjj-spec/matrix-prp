package io.micor.prp.health;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.keycloak.util.JsonSerialization;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.interfaces.RSAPublicKey;
import java.util.*;
/** Offline tests of the exact normalizer called by the deployed executor. */
public class MetadataRulesTest {
 static int count=0;
 static byte[] bytes(ObjectNode n){return n.toString().getBytes(StandardCharsets.UTF_8);}
 static void negative(String name,ObjectNode n,ObjectNode keys)throws Exception{
  boolean rejected=false;try{HealthCimdMetadata.normalize(bytes(n),bytes(keys));}catch(Exception expected){rejected=true;}
  if(!rejected)throw new AssertionError(name);count++;System.out.println("PASS NORMALIZER "+name);
 }
 public static void main(String[] args)throws Exception{
  ObjectNode m=JsonSerialization.mapper.createObjectNode();
  m.put("client_id",HealthCimdMetadata.ID);m.put("client_uri","https://chatgpt.com/");m.put("logo_uri","https://persistent.oaistatic.com/sonic/misc/openai-logo.png");
  m.putArray("redirect_uris").add(HealthCimdMetadata.REDIRECT);m.putArray("grant_types").add("authorization_code").add("refresh_token");m.putArray("response_types").add("code");
  // Actual ChatGPT RP Metadata Choices normally provides the plural field only.
  m.putArray("token_endpoint_auth_methods_supported").add("none").add("private_key_jwt");m.put("jwks_uri",HealthCimdMetadata.JWKS);
  KeyPairGenerator gen=KeyPairGenerator.getInstance("RSA");gen.initialize(2048);RSAPublicKey pub=(RSAPublicKey)gen.generateKeyPair().getPublic();
  ObjectNode keys=JsonSerialization.mapper.createObjectNode(),key=JsonSerialization.mapper.createObjectNode();key.put("kty","RSA");key.put("kid","unit-public-only");key.put("alg","RS256");key.put("use","sig");key.put("n",Base64.getUrlEncoder().withoutPadding().encodeToString(pub.getModulus().toByteArray()));key.put("e","AQAB");keys.putArray("keys").add(key);
  var dto=HealthCimdMetadata.normalize(bytes(m),bytes(keys));if(!HealthCimdMetadata.ID.equals(dto.getClientId())||!"private_key_jwt".equals(dto.getTokenEndpointAuthMethod()))throw new AssertionError();count++;System.out.println("PASS NORMALIZER positive preserves identity and method");
  ObjectNode n=m.deepCopy();n.put("token_endpoint_auth_method","private_key_jwt");
  var explicit=HealthCimdMetadata.normalize(bytes(n),bytes(keys));
  if(!"private_key_jwt".equals(explicit.getTokenEndpointAuthMethod()))throw new AssertionError("explicit method");
  count++;System.out.println("PASS NORMALIZER explicit matching method");
  n=m.deepCopy();n.put("unknown_security_field",true);negative("native unknown field strict",n,keys);
  n=m.deepCopy();n.put("token_endpoint_auth_method","none");negative("none refused",n,keys);
  n=m.deepCopy();n.putNull("token_endpoint_auth_method");negative("null singular method refused",n,keys);
  n=m.deepCopy();n.put("token_endpoint_auth_method","client_secret_post");negative("secret refused",n,keys);
  n=m.deepCopy();n.putArray("token_endpoint_auth_methods_supported").add("none");negative("missing private choice",n,keys);
  n=m.deepCopy();n.putArray("token_endpoint_auth_methods_supported").add("private_key_jwt").add("private_key_jwt");negative("duplicate choices",n,keys);
  n=m.deepCopy();n.putArray("redirect_uris").add(HealthCimdMetadata.REDIRECT+"/");negative("callback mismatch",n,keys);
  n=m.deepCopy();n.put("client_id",HealthCimdMetadata.ID+"?x=1");negative("client mismatch",n,keys);
  n=m.deepCopy();n.put("client_uri","https://evil.example/");negative("client URI mismatch",n,keys);
  n=m.deepCopy();n.put("logo_uri","https://persistent.oaistatic.com/other.png");negative("logo path not broadly trusted",n,keys);
  n=m.deepCopy();n.put("tos_uri","https://evil.example/");negative("unreviewed optional URL",n,keys);
  n=m.deepCopy();n.put("jwks_uri","https://127.0.0.1/keys");negative("private JWKS URI",n,keys);
  n=m.deepCopy();n.put("jwks_uri","https://chatgpt.com/other/keys");negative("JWKS path mismatch",n,keys);
  ObjectNode k=keys.deepCopy();((ObjectNode)k.path("keys").get(0)).put("d","not-a-real-key");negative("private JWK field",m,k);
  System.out.println("NORMALIZER_COMPLETE "+count);
 }
}
