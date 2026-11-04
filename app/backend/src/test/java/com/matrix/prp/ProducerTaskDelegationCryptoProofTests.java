package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Date;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.HashMap;
import java.util.HashSet;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

/**
 * TEST-ONLY executable proof of cryptographic delegated identity checks.
 *
 * Not a Spring @Component, no producer endpoint, no production keys, no
 * persistent grant table and no service-peer mTLS implementation. In
 * particular, JwtDecoder verification is NOT service-peer authentication.
 * These in-memory owner mappings are synthetic and confer no real consent.
 */
class ProducerTaskDelegationCryptoProofTests {
    private static final String ISSUER = "https://ci-issuer.invalid/realms/synthetic";
    private static final String AUDIENCE = "prp-production-task-read-producer";
    private static final String CLIENT = "https://chatgpt.com/oauth/client.json";
    private static final String SERVICE = "synthetic-review-mcp-bridge";
    private static final String SCOPE = "prp.tasks.read";

    private KeyPair signer;
    private KeyPair attacker;
    private ProofOnlyVerifier verifier;

    private static KeyPair keypair() throws Exception {
        var generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    @BeforeEach
    void init() throws Exception {
        signer = keypair();
        attacker = keypair();
        verifier = new ProofOnlyVerifier((RSAPublicKey) signer.getPublic());
        verifier.ownerByExternalSubject.put("synthetic-owner-a", 12001L);
        verifier.ownerByExternalSubject.put("synthetic-owner-b", 12002L);
        verifier.activeOwners.addAll(Set.of(12001L, 12002L));
        verifier.consents.addAll(Set.of(12001L, 12002L));
    }

    private static String signed(KeyPair key, String iss, String aud, String sub,
                                 String client, String service, List<String> scopes,
                                 String jti, long expiryOffsetSeconds) throws Exception {
        Instant now = Instant.now();
        JWTClaimsSet claims = new JWTClaimsSet.Builder()
            .issuer(iss).subject(sub).audience(aud)
            .issueTime(Date.from(now.minusSeconds(3)))
            .notBeforeTime(Date.from(now.minusSeconds(3)))
            .expirationTime(Date.from(now.plusSeconds(expiryOffsetSeconds)))
            .jwtID(jti).claim("client_id", client).claim("service_id", service)
            .claim("scp", scopes).build();
        SignedJWT jwt = new SignedJWT(new JWSHeader.Builder(JWSAlgorithm.RS256).build(), claims);
        jwt.sign(new RSASSASigner(key.getPrivate()));
        return jwt.serialize();
    }

    private String token(String subject) throws Exception {
        return signed(signer, ISSUER, AUDIENCE, subject, CLIENT, SERVICE,
            List.of(SCOPE), UUID.randomUUID().toString(), 120);
    }

    private static final class ProofOnlyVerifier {
        final JwtDecoder decoder;
        final Map<String, Long> ownerByExternalSubject = new HashMap<>();
        final Set<Long> activeOwners = new HashSet<>();
        final Set<Long> consents = new HashSet<>();
        final Set<String> consumedJti = new HashSet<>();

        ProofOnlyVerifier(RSAPublicKey verifiedPublicKey) {
            NimbusJwtDecoder configured = NimbusJwtDecoder.withPublicKey(verifiedPublicKey)
                .signatureAlgorithm(org.springframework.security.oauth2.jose.jws.SignatureAlgorithm.RS256)
                .build();
            configured.setJwtValidator(jwt -> {
                var standard = JwtValidators.createDefaultWithIssuer(ISSUER).validate(jwt);
                if (standard.hasErrors()) return standard;
                boolean exactAudience = jwt.getAudience().size() == 1
                    && AUDIENCE.equals(jwt.getAudience().getFirst());
                return exactAudience ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error("invalid_token", "Wrong producer audience", null));
            });
            decoder = configured;
        }

        long ownerOfDecodedProof(String compactSignedJwt) {
            // The decode method verifies the RS256 signature, standard
            // timestamps, trusted issuer and exact audience BEFORE any mapping.
            Jwt jwt = decoder.decode(compactSignedJwt);
            String subject = jwt.getSubject();
            String jti = jwt.getId();
            List<String> scopes = jwt.getClaimAsStringList("scp");
            if (subject == null || subject.isBlank()
                || !CLIENT.equals(jwt.getClaimAsString("client_id"))
                || !SERVICE.equals(jwt.getClaimAsString("service_id"))
                || scopes == null || !scopes.contains(SCOPE)
                || jti == null || !jti.matches("[A-Za-z0-9-]{16,128}")) {
                throw new SecurityException("Unsigned/unauthorized delegation claims");
            }
            Long owner = ownerByExternalSubject.get(subject);
            if (owner == null || !activeOwners.contains(owner) || !consents.contains(owner))
                throw new SecurityException("No current verified producer-owner consent");
            // At-most-once test behavior; a real producer needs a shared,
            // expiring atomic replay registry across multiple instances.
            if (!consumedJti.add(jti))
                throw new SecurityException("Delegation request was replayed");
            return owner;
        }
    }

    @Test void twoSignedSyntheticSubjectsMapToDifferentProducerOwners() throws Exception {
        assertThat(verifier.ownerOfDecodedProof(token("synthetic-owner-a"))).isEqualTo(12001);
        assertThat(verifier.ownerOfDecodedProof(token("synthetic-owner-b"))).isEqualTo(12002);
    }

    @Test void attackersSignatureMustFailBeforeOwnerLookup() throws Exception {
        String forged = signed(attacker, ISSUER, AUDIENCE, "synthetic-owner-a",
            CLIENT, SERVICE, List.of(SCOPE), UUID.randomUUID().toString(), 120);
        assertThatThrownBy(() -> verifier.ownerOfDecodedProof(forged))
            .isInstanceOf(JwtException.class);
    }

    @Test void wrongIssuerOrProducerAudienceFailsCryptographicValidation() throws Exception {
        for (String[] mutated : List.of(
            new String[]{"https://malicious.invalid", AUDIENCE},
            new String[]{ISSUER, "prp-other-api"},
            new String[]{ISSUER, "https://prp-test.micor.top/api/mcp"}
        )) {
            String bad = signed(signer, mutated[0], mutated[1], "synthetic-owner-a",
                CLIENT, SERVICE, List.of(SCOPE), UUID.randomUUID().toString(), 120);
            assertThatThrownBy(() -> verifier.ownerOfDecodedProof(bad))
                .isInstanceOf(JwtException.class);
        }
    }

    @Test void revokedConsentAndDisabledOwnerCannotUseOtherwiseValidSignature() throws Exception {
        String formerlyValid = token("synthetic-owner-a");
        verifier.consents.remove(12001L);
        assertThatThrownBy(() -> verifier.ownerOfDecodedProof(formerlyValid))
            .isInstanceOf(SecurityException.class);
        verifier.consents.add(12001L);
        verifier.activeOwners.remove(12001L);
        assertThatThrownBy(() -> verifier.ownerOfDecodedProof(formerlyValid))
            .isInstanceOf(SecurityException.class);
    }

    @Test void unlinkedSubjectAndIncorrectClientOrPeerClaimsFail() throws Exception {
        String unlinked = token("unknown-subject");
        assertThatThrownBy(() -> verifier.ownerOfDecodedProof(unlinked))
            .isInstanceOf(SecurityException.class);
        for (String[] wrong : List.of(
            new String[]{"wrong-client", SERVICE},
            new String[]{CLIENT, "different-workload"}
        )) {
            String forgedClaim = signed(signer, ISSUER, AUDIENCE, "synthetic-owner-a",
                wrong[0], wrong[1], List.of(SCOPE), UUID.randomUUID().toString(), 120);
            assertThatThrownBy(() -> verifier.ownerOfDecodedProof(forgedClaim))
                .isInstanceOf(SecurityException.class);
        }
    }

    @Test void financeOnlyScopeMissingJtiAndExpiredDelegationFail() throws Exception {
        for (String invalid : List.of(
            signed(signer, ISSUER, AUDIENCE, "synthetic-owner-a", CLIENT, SERVICE,
                List.of("prp.finance.read"), UUID.randomUUID().toString(), 120),
            signed(signer, ISSUER, AUDIENCE, "synthetic-owner-a", CLIENT, SERVICE,
                List.of(SCOPE), null, 120)
        )) {
            assertThatThrownBy(() -> verifier.ownerOfDecodedProof(invalid))
                .isInstanceOf(SecurityException.class);
        }
        String expired = signed(signer, ISSUER, AUDIENCE, "synthetic-owner-a",
            CLIENT, SERVICE, List.of(SCOPE), UUID.randomUUID().toString(), -600);
        assertThatThrownBy(() -> verifier.ownerOfDecodedProof(expired))
            .isInstanceOf(JwtException.class);
    }

    @Test void replayOfSameSignedRequestFailsEvenBeforeAnyDatabaseRead() throws Exception {
        String proof = token("synthetic-owner-a");
        assertThat(verifier.ownerOfDecodedProof(proof)).isEqualTo(12001);
        assertThatThrownBy(() -> verifier.ownerOfDecodedProof(proof))
            .isInstanceOf(SecurityException.class);
    }
}
