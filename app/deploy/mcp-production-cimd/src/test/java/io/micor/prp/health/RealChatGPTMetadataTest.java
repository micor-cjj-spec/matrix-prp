package io.micor.prp.health;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Set;
import com.fasterxml.jackson.databind.JsonNode;
import org.keycloak.util.JsonSerialization;
import static org.junit.jupiter.api.Assertions.*;

/** CI-only live public metadata contract; no OAuth JWT or user credentials. */
@EnabledIfEnvironmentVariable(named = "PRP_PUBLIC_CHATGPT_METADATA_PROBE", matches = "1")
class RealChatGPTMetadataTest {
  private static byte[] publicDocument(HttpClient client, String uri) throws Exception {
    HttpRequest req = HttpRequest.newBuilder(URI.create(uri))
        .GET().header("Accept", "application/json")
        .timeout(Duration.ofSeconds(12)).build();
    HttpResponse<byte[]> response = client.send(req, HttpResponse.BodyHandlers.ofByteArray());
    assertEquals(200, response.statusCode(), "public metadata fetch status");
    assertTrue(response.headers().firstValue("content-type").orElse("")
        .toLowerCase(java.util.Locale.ROOT).startsWith("application/json"),
        "public metadata must be JSON");
    assertTrue(response.body().length > 0 && response.body().length <= 65536,
        "bounded public metadata document");
    return response.body();
  }

  @Test @Timeout(35)
  void currentOpenAiPublicCimdAndJwksAcceptedByStrictNormalizer() throws Exception {
    HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(7))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
    byte[] clientJson = publicDocument(client, HealthCimdMetadata.ID);
    byte[] jwksJson = publicDocument(client, HealthCimdMetadata.JWKS);
    JsonNode metadata = JsonSerialization.mapper.readTree(clientJson);
    assertEquals(HealthCimdMetadata.ID, metadata.path("client_id").asText());
    assertEquals(HealthCimdMetadata.JWKS, metadata.path("jwks_uri").asText());
    assertEquals("private_key_jwt", metadata.path("token_endpoint_auth_method").asText());
    assertEquals("RS256", metadata.path("token_endpoint_auth_signing_alg").asText());
    assertEquals(Set.of("private_key_jwt", "none"),
        java.util.stream.StreamSupport.stream(
            metadata.path("token_endpoint_auth_methods_supported").spliterator(), false)
            .map(JsonNode::asText).collect(java.util.stream.Collectors.toSet()));
    JsonNode keys = JsonSerialization.mapper.readTree(jwksJson).path("keys");
    assertTrue(keys.isArray() && !keys.isEmpty() && keys.size() <= 4);
    for (JsonNode k : keys) {
      assertEquals("RSA", k.path("kty").asText());
      assertTrue(k.hasNonNull("kid") && k.hasNonNull("n") && k.hasNonNull("e"));
      assertFalse(k.has("d") || k.has("p") || k.has("q"));
    }
    var normalized = HealthCimdMetadata.normalize(clientJson, jwksJson);
    assertEquals(HealthCimdMetadata.ID, normalized.getClientId());
    assertEquals("private_key_jwt", normalized.getTokenEndpointAuthMethod());
    System.out.println("PASS CIMD_LIVE_PUBLIC_METADATA_NORM");
    System.out.println("RAW_JWKS_OR_CREDENTIALS_PRINTED=False");
    System.out.println("REAL_CHATGPT_ASSERTION_TESTED=False");
  }
}
