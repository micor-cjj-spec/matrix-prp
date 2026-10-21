package com.matrix.prp.mcp;

import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.KeyUse;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import com.sun.net.httpserver.HttpServer;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.time.Duration;
import java.util.Date;
import java.util.List;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * Local-only cryptographic test: Spring's real JWKS verifier, without a mock
 * decoder, an external identity provider or any test bearer logged to CI.
 */
class McpOAuthJwtValidationTests {
    @Test
    void stalledJwksFailsWithinBoundWithoutAuthenticating() throws Exception {
        HttpServer stalled = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        stalled.createContext("/stall", exchange -> {
            try { Thread.sleep(8000); }
            catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); }
            finally { exchange.close(); }
        });
        stalled.start();
        try {
            var decoder = McpOAuthResourceServerConfig.jwksDecoder(
                "http://127.0.0.1:" + stalled.getAddress().getPort() + "/stall");
            String token = signedToken(trusted, ISSUER, RESOURCE, Instant.now().plusSeconds(360));
            org.junit.jupiter.api.Assertions.assertTimeoutPreemptively(Duration.ofSeconds(10), () ->
                assertThatThrownBy(() -> decoder.decode(token)).isInstanceOf(JwtException.class));
        } finally { stalled.stop(0); }
    }
    private static final String ISSUER = "https://issuer.example.test/realms/prp-mcp";
    private static final String RESOURCE = "https://prp.example.test/api/mcp";
    private static HttpServer jwks;
    private static KeyPair trusted;
    private static KeyPair attacker;
    private static String jwksUri;

    @BeforeAll
    static void setup() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        trusted = generator.generateKeyPair();
        attacker = generator.generateKeyPair();
        var publicKey = new RSAKey.Builder((RSAPublicKey) trusted.getPublic())
            .keyID("mcp-test-key-1").keyUse(KeyUse.SIGNATURE)
            .algorithm(JWSAlgorithm.RS256).build();
        byte[] keys = new JWKSet(publicKey).toString().getBytes(StandardCharsets.UTF_8);
        jwks = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        jwks.createContext("/jwks.json", exchange -> {
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, keys.length);
            try (var output = exchange.getResponseBody()) {
                output.write(keys);
            }
        });
        jwks.start();
        jwksUri = "http://127.0.0.1:" + jwks.getAddress().getPort() + "/jwks.json";
    }

    @AfterAll
    static void tearDown() {
        if (jwks != null) jwks.stop(0);
    }

    private static NimbusJwtDecoder verifier() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder.withJwkSetUri(jwksUri).build();
        decoder.setJwtValidator(McpOAuthResourceServerConfig.jwtValidator(ISSUER, RESOURCE));
        return decoder;
    }

    private static String signedToken(KeyPair signer, String issuer, String audience, Instant expiry)
            throws Exception {
        return signedToken(signer, issuer, List.of(audience), expiry);
    }

    private static String signedToken(KeyPair signer, String issuer, List<String> audiences, Instant expiry)
            throws Exception {
        var claims = new JWTClaimsSet.Builder()
            .issuer(issuer)
            .subject("oauth-user-123")
            .audience(audiences)
            .issueTime(Date.from(Instant.now().minusSeconds(20)))
            .expirationTime(Date.from(expiry))
            .claim("client_id", "trusted-oauth-client")
            .claim("scope", "prp.tasks.read")
            .build();
        var token = new SignedJWT(new JWSHeader.Builder(JWSAlgorithm.RS256)
            .keyID("mcp-test-key-1").build(), claims);
        token.sign(new RSASSASigner(signer.getPrivate()));
        return token.serialize();
    }

    @Test
    void acceptsGenuineIssuerSignatureForExactMcpAudience() throws Exception {
        var jwt = verifier().decode(signedToken(trusted, ISSUER, RESOURCE, Instant.now().plusSeconds(360)));
        assertThat(jwt.getAudience()).containsExactly(RESOURCE);
        assertThat(jwt.getSubject()).isEqualTo("oauth-user-123");
    }

    @Test
    void acceptsAuth0StyleAdditionalUserinfoAudienceWhenExactMcpAudienceIsPresent() throws Exception {
        var jwt = verifier().decode(signedToken(trusted, ISSUER,
            List.of(RESOURCE, ISSUER + "/userinfo"), Instant.now().plusSeconds(360)));
        assertThat(jwt.getAudience()).contains(RESOURCE);
        assertThat(jwt.getAudience()).contains(ISSUER + "/userinfo");
    }

    @Test
    void rejectsOtherApiEvenWhenAdditionalUserinfoAudienceIsPresent() throws Exception {
        String token = signedToken(trusted, ISSUER,
            List.of("https://another-api.example.test/api/mcp", ISSUER + "/userinfo"),
            Instant.now().plusSeconds(360));
        assertThatThrownBy(() -> verifier().decode(token)).isInstanceOf(JwtException.class);
    }

    @Test
    void rejectsAttackerSignedTokenEvenWithExpectedKeyIdAndClaims() throws Exception {
        String token = signedToken(attacker, ISSUER, RESOURCE, Instant.now().plusSeconds(360));
        assertThatThrownBy(() -> verifier().decode(token)).isInstanceOf(JwtException.class);
    }

    @Test
    void rejectsWrongIssuerEvenIfSignatureIsValid() throws Exception {
        String token = signedToken(trusted, "https://malicious.example.test/realms/prp-mcp",
            RESOURCE, Instant.now().plusSeconds(360));
        assertThatThrownBy(() -> verifier().decode(token)).isInstanceOf(JwtException.class);
    }

    @Test
    void rejectsWrongAudienceEvenIfSignatureAndIssuerAreValid() throws Exception {
        String token = signedToken(trusted, ISSUER, "https://other-api.example.test/api/mcp",
            Instant.now().plusSeconds(360));
        assertThatThrownBy(() -> verifier().decode(token)).isInstanceOf(JwtException.class);
    }

    @Test
    void rejectsExpiredAccessTokenEvenIfSignatureIsValid() throws Exception {
        String token = signedToken(trusted, ISSUER, RESOURCE, Instant.now().minusSeconds(300));
        assertThatThrownBy(() -> verifier().decode(token)).isInstanceOf(JwtException.class);
    }
}
