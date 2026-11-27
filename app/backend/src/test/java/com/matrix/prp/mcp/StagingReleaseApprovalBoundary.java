package com.matrix.prp.mcp;

import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.auth.repository.UserStore;
import jakarta.servlet.http.HttpServletRequest;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.PublicKey;
import java.security.Signature;
import java.time.Clock;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.function.LongSupplier;
import java.util.function.Supplier;
import org.springframework.security.core.Authentication;

/**
 * Test-source-only P3.5 identity and independent decision proof prototype.
 * Not packaged into the backend jar; no bean, route, tool, config, DB write,
 * trusted host proof issuer or executor. All decisions are rehearsal receipts.
 */
final class StagingReleaseApprovalBoundary {
    static final String ENVIRONMENT = "prp-unified-396";
    static final String CLIENT = "https://chatgpt.com/oauth/client.json";
    // Proposed test contract only. This scope is NOT registered or granted.
    static final String SCOPE = "prp.release.staging.review";
    static final String SESSION_ATTRIBUTE = "prp.release.rehearsal.verifiedSession";
    private static final String DOMAIN = "PRP-P35-STAGING-REVIEW-ONLY-V1";
    private static final int MAX_RECORDS = 128;
    private static final long MAX_REQUEST_TTL = 900;
    private static final long MAX_PROOF_TTL = 60;

    enum Decision { APPROVE, REJECT }

    // Must originate from a future trusted session bridge, never a header or tool arg.
    record VerifiedSession(String digest) {}

    // Server-owned pending record, including current evidence digest. A future
    // adapter must refresh the candidate/evidence and obtain this from its
    // trusted store, not deserialize it from the card or model.
    record Pending(UUID approvalId, long ownerId, String sessionDigest,
                   String commit, String artifactDigest, int schema,
                   long ciRun, int ciAttempt, String evidenceDigest,
                   long createdAt, long expiresAt) {}

    // The envelope cannot supply owner, environment, candidate, session or clock.
    record Envelope(UUID approvalId, Decision decision, UUID nonce, long issuedAt,
                    long expiresAt, byte[] signature) {
        Envelope {
            signature = signature == null ? null : signature.clone();
        }
        @Override public byte[] signature() {
            return signature == null ? null : signature.clone();
        }
    }

    record Receipt(UUID approvalId, Decision decision, String state, String environment,
                   boolean deploymentAuthorized, boolean productionAuthorized,
                   boolean releaseEligible, boolean liveVerified) {}

    private final UserStore users;
    private final McpClientGrantService grants;
    private final long allowedOwner;
    private final PublicKey proofKey;
    private final Clock clock;
    private final DecisionJournal journal;

    enum GateState { PASS, BLOCKED, UNKNOWN }

    // A server-side fixture source, not a tool/card field. No authoritative
    // collector is connected in this test-only prototype.
    record CurrentReview(Pending pending, GateState gates) {}

    interface DecisionJournal {
        void record(Pending pending, Envelope envelope, LongSupplier lockedRecheck);
    }

    private static final class MemoryJournal implements DecisionJournal {
        private final Set<UUID> decided = new HashSet<>();
        private final Set<UUID> usedNonces = new HashSet<>();
        private long lastTime;

        @Override public synchronized void record(Pending pending, Envelope envelope, LongSupplier lockedRecheck) {
            long now = lockedRecheck.getAsLong();
            require(now >= lastTime, "INVALID_SERVER_CLOCK");
            require(!decided.contains(pending.approvalId()) && !usedNonces.contains(envelope.nonce()),
                    "REPLAY_OR_ALREADY_DECIDED");
            require(decided.size() < MAX_RECORDS && usedNonces.size() < MAX_RECORDS,
                    "REHEARSAL_CAPACITY");
            lastTime = now;
            decided.add(pending.approvalId());
            usedNonces.add(envelope.nonce());
        }
    }

    StagingReleaseApprovalBoundary(UserStore users, McpClientGrantService grants,
                                   long allowedOwner, PublicKey proofKey, Clock clock) {
        this(users, grants, allowedOwner, proofKey, clock, new MemoryJournal());
    }

    StagingReleaseApprovalBoundary(UserStore users, McpClientGrantService grants,
                                   long allowedOwner, PublicKey proofKey, Clock clock,
                                   DecisionJournal journal) {
        require(allowedOwner > 0 && proofKey != null && clock != null
                && users != null && grants != null && journal != null, "INVALID_REHEARSAL_CONFIG");
        this.users = users;
        this.grants = grants;
        this.allowedOwner = allowedOwner;
        this.proofKey = proofKey;
        this.clock = clock;
        this.journal = journal;
    }

    synchronized Receipt submit(HttpServletRequest request, Pending pending, Envelope envelope,
                                Supplier<CurrentReview> current) {
        long started = clock.instant().getEpochSecond();
        require(started > 0, "INVALID_SERVER_CLOCK");
        require(request != null && pending != null && envelope != null && current != null, "MISSING_REVIEW");
        validatePending(pending, started);
        authenticate(request, pending);
        validateEnvelope(pending, envelope, started);
        byte[] signature = envelope.signature();
        require(signature != null && signature.length == 64, "INVALID_INDEPENDENT_PROOF");
        verify(signature, signedBytes(pending, envelope));
        // Both journals invoke this callback after taking their exclusive lock,
        // before inserting a receipt. Never trust the time sampled before a wait.
        journal.record(pending, envelope, () -> {
            CurrentReview fresh = current.get();
            require(fresh != null && fresh.gates() == GateState.PASS, "CURRENT_GATES_NOT_PASS");
            require(pending.equals(fresh.pending()), "CURRENT_REVIEW_CHANGED");
            authenticate(request, pending);
            long now = clock.instant().getEpochSecond();
            require(now >= started, "INVALID_SERVER_CLOCK");
            validatePending(pending, now);
            validateEnvelope(pending, envelope, now);
            return now;
        });
        return new Receipt(pending.approvalId(), envelope.decision(), "REVIEW_RECORDED_ONLY",
                ENVIRONMENT, false, false, false, false);
    }

    private static void validateEnvelope(Pending pending, Envelope envelope, long now) {
        require(validId(envelope.approvalId()) && envelope.approvalId().equals(pending.approvalId())
                && validId(envelope.nonce()) && envelope.decision() != null,
                "INVALID_DECISION_BINDING");
        require(envelope.issuedAt() >= pending.createdAt() && envelope.issuedAt() <= now
                && envelope.expiresAt() > now && envelope.expiresAt() <= pending.expiresAt()
                && envelope.expiresAt() - envelope.issuedAt() <= MAX_PROOF_TTL,
                "PROOF_EXPIRED_OR_FUTURE");
    }

    private void authenticate(HttpServletRequest request, Pending pending) {
        Object saved = request.getAttribute(McpOAuthTransportConfiguration.VERIFIED_AUTH);
        require(saved instanceof Authentication, "VERIFIED_OAUTH_REQUIRED");
        Authentication auth = (Authentication) saved;
        require(auth.isAuthenticated() && auth.getPrincipal() instanceof UserProfile
                && auth.getDetails() instanceof McpScopeGuard.VerifiedClient,
                "VERIFIED_OAUTH_REQUIRED");
        UserProfile profile = (UserProfile) auth.getPrincipal();
        McpScopeGuard.VerifiedClient client = (McpScopeGuard.VerifiedClient) auth.getDetails();
        require(profile.id() == allowedOwner && profile.id() == pending.ownerId(),
                "RELEASE_OWNER_REQUIRED");
        require(CLIENT.equals(client.clientId()) && client.grantedScopes().contains(SCOPE)
                && auth.getAuthorities().stream()
                    .anyMatch(a -> ("SCOPE_" + SCOPE).equals(a.getAuthority())),
                "REVIEW_SCOPE_REQUIRED");
        // Check current account and grant as well as the captured identity.
        UserAccount account = users.findById(profile.id()).orElse(null);
        require(account != null && account.enabled() && account.id() == profile.id()
                && Objects.equals(account.username(), profile.username()), "ACCOUNT_UNAVAILABLE");
        require(grants.grantedScopes(profile.id(), CLIENT).contains(SCOPE), "REVIEW_GRANT_REVOKED");
        Object session = request.getAttribute(SESSION_ATTRIBUTE);
        require(session instanceof VerifiedSession verified
                && validDigest(verified.digest()) && verified.digest().equals(pending.sessionDigest()),
                "VERIFIED_SESSION_MISMATCH");
    }

    private void validatePending(Pending p, long now) {
        require(validId(p.approvalId()) && p.ownerId() == allowedOwner && validDigest(p.sessionDigest())
                && p.commit() != null && p.commit().matches("[0-9a-f]{40}")
                && validDigest(p.artifactDigest()) && validDigest(p.evidenceDigest())
                && p.schema() > 0 && p.schema() <= 1000000 && p.ciRun() > 0 && p.ciAttempt() > 0,
                "INVALID_PENDING_BINDING");
        require(p.createdAt() > 0 && p.createdAt() <= now && p.expiresAt() > now
                && p.expiresAt() - p.createdAt() <= MAX_REQUEST_TTL, "PENDING_EXPIRED_OR_FUTURE");
    }

    private static boolean validId(UUID id) {
        return id != null && id.version() == 4 && id.variant() == 2;
    }

    private static boolean validDigest(String value) {
        return value != null && value.matches("sha256:[0-9a-f]{64}");
    }

    // Unambiguous fixed-field encoding: all string/UUID/digest/enum inputs
    // validated to exclude line breaks; numbers canonical decimal. Domain and
    // exact environment/client are fixed, never accepted from the envelope.
    static byte[] signedBytes(Pending p, Envelope e) {
        return String.join("\n", DOMAIN, ENVIRONMENT, CLIENT, SCOPE,
                p.approvalId().toString(), Long.toString(p.ownerId()), p.sessionDigest(),
                p.commit(), p.artifactDigest(), Integer.toString(p.schema()),
                Long.toString(p.ciRun()), Integer.toString(p.ciAttempt()), p.evidenceDigest(),
                Long.toString(p.createdAt()), Long.toString(p.expiresAt()),
                e.decision().name(), e.nonce().toString(),
                Long.toString(e.issuedAt()), Long.toString(e.expiresAt()))
                .getBytes(StandardCharsets.US_ASCII);
    }

    private void verify(byte[] bytes, byte[] message) {
        try {
            Signature verifier = Signature.getInstance("Ed25519");
            verifier.initVerify(proofKey);
            verifier.update(message);
            require(verifier.verify(bytes), "INVALID_INDEPENDENT_PROOF");
        } catch (GeneralSecurityException ex) {
            throw new IllegalArgumentException("INVALID_INDEPENDENT_PROOF");
        }
    }

    private static void require(boolean ok, String reason) {
        if (!ok) throw new IllegalArgumentException(reason);
    }
}
