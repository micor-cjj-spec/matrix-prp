package com.matrix.prp.mcp;

import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.auth.repository.UserStore;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Consumer;
import java.util.concurrent.Executors;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static com.matrix.prp.mcp.StagingReleaseApprovalBoundary.*;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

class StagingReleaseDecisionJournalIT {
    private static final long NOW = 1700000000L;
    private static final long OWNER = 7;
    private static final String SESSION = "sha256:" + "1".repeat(64);
    private final UserStore users = mock(UserStore.class);
    private final McpClientGrantService grants = mock(McpClientGrantService.class);
    private String suffix;
    private StagingReleaseDecisionJournal journal;
    private KeyPair keys;
    private Pending pending;

    @BeforeEach void setup() throws Exception {
        suffix = StagingReleaseDecisionJournal.newSuffix();
        journal = new StagingReleaseDecisionJournal(suffix);
        journal.initialize();
        keys = KeyPairGenerator.getInstance("Ed25519").generateKeyPair();
        when(users.findById(OWNER)).thenReturn(Optional.of(
            new UserAccount(OWNER,"owner","Synthetic owner","unused-test-hash",false,true)));
        when(grants.grantedScopes(OWNER,CLIENT)).thenReturn(Set.of(SCOPE));
        pending = candidate();
    }

    @AfterEach void cleanup() throws Exception {
        if (journal != null) journal.cleanup();
    }

    private Pending candidate() {
        return new Pending(UUID.randomUUID(),OWNER,SESSION,"a".repeat(40),"sha256:"+"2".repeat(64),
            30,123,1,"sha256:"+"3".repeat(64),NOW-30,NOW+300);
    }

    private StagingReleaseApprovalBoundary reopen(long now) {
        return new StagingReleaseApprovalBoundary(users,grants,OWNER,keys.getPublic(),
            Clock.fixed(Instant.ofEpochSecond(now),ZoneOffset.UTC),new StagingReleaseDecisionJournal(suffix));
    }

    private MockHttpServletRequest request() {
        var auth = new UsernamePasswordAuthenticationToken(new UserProfile(OWNER,"owner","Synthetic owner"),
            null,List.of(new SimpleGrantedAuthority("SCOPE_"+SCOPE)));
        auth.setDetails(new McpScopeGuard.VerifiedClient(CLIENT,Set.of(SCOPE)));
        var req = new MockHttpServletRequest();
        req.setAttribute(McpOAuthTransportConfiguration.VERIFIED_AUTH,auth);
        req.setAttribute(SESSION_ATTRIBUTE,new VerifiedSession(SESSION));
        return req;
    }

    private Envelope proof(Pending p,Decision decision,UUID nonce) throws Exception {
        var unsigned = new Envelope(p.approvalId(),decision,nonce,NOW-1,NOW+30,null);
        var sign = Signature.getInstance("Ed25519");
        sign.initSign(keys.getPrivate());
        sign.update(signedBytes(p,unsigned));
        return new Envelope(p.approvalId(),decision,nonce,NOW-1,NOW+30,sign.sign());
    }

    @Test void persistedDecisionRejectsReplayAfterReopen() throws Exception {
        Envelope e = proof(pending,Decision.APPROVE,UUID.randomUUID());
        var result = submitFixture(reopen(NOW),request(),pending,e);
        assertThat(result.state()).isEqualTo("REVIEW_RECORDED_ONLY");
        assertThat(result.deploymentAuthorized() || result.productionAuthorized()
            || result.releaseEligible() || result.liveVerified()).isFalse();
        assertThatThrownBy(() -> submitFixture(reopen(NOW+1),request(),pending,e))
            .hasMessage("REPLAY_OR_ALREADY_DECIDED");
        assertThat(journal.count()).isEqualTo(1);
    }

    @Test void independentConnectionsCompetingForSameApprovalCommitOnlyOne() throws Exception {
        Envelope a = proof(pending,Decision.APPROVE,UUID.randomUUID());
        Envelope b = proof(pending,Decision.REJECT,UUID.randomUUID());
        try (var pool = Executors.newFixedThreadPool(2)) {
            Callable<String> first = () -> outcome(a);
            Callable<String> second = () -> outcome(b);
            var outcomes = pool.invokeAll(List.of(first,second));
            assertThat(List.of(outcomes.get(0).get(),outcomes.get(1).get()))
                .containsExactlyInAnyOrder("REVIEW_RECORDED_ONLY","REPLAY_OR_ALREADY_DECIDED");
        }
        assertThat(journal.count()).isEqualTo(1);
    }

    private Receipt submitFixture(StagingReleaseApprovalBoundary b,
                                  MockHttpServletRequest req, Pending reviewed, Envelope e) {
        return b.submit(req, reviewed, e, () -> new CurrentReview(reviewed, GateState.PASS));
    }

    private String outcome(Envelope e) {
        try { return submitFixture(reopen(NOW),request(),pending,e).state(); }
        catch (IllegalArgumentException e1) { return e1.getMessage(); }
    }

    @Test void nonceUniquenessPersistsAcrossDistinctRequests() throws Exception {
        UUID nonce = UUID.randomUUID();
        submitFixture(reopen(NOW),request(),pending,proof(pending,Decision.APPROVE,nonce));
        Pending other = candidate();
        Envelope e = proof(other,Decision.REJECT,nonce);
        assertThatThrownBy(() -> submitFixture(reopen(NOW+1),request(),other,e))
            .hasMessage("REPLAY_OR_ALREADY_DECIDED");
        assertThat(journal.count()).isEqualTo(1);
    }

    @Test void failedMetadataUpdateRollsBackInsertedReceipt() throws Exception {
        journal.breakMetadataUpdate();
        Envelope e = proof(pending,Decision.APPROVE,UUID.randomUUID());
        assertThatThrownBy(() -> submitFixture(reopen(NOW),request(),pending,e))
            .hasMessage("TEST_JOURNAL_UNAVAILABLE");
        assertThat(journal.count()).isZero();
    }

    @Test void persistentClockRejectsRewindAcrossInstances() throws Exception {
        submitFixture(reopen(NOW+1),request(),pending,proof(pending,Decision.APPROVE,UUID.randomUUID()));
        Pending other = candidate();
        Envelope e = proof(other,Decision.APPROVE,UUID.randomUUID());
        assertThatThrownBy(() -> submitFixture(reopen(NOW),request(),other,e))
            .hasMessage("INVALID_SERVER_CLOCK");
        assertThat(journal.count()).isEqualTo(1);
    }

    @Test void invalidProofCannotWriteReceipt() throws Exception {
        Envelope valid = proof(pending,Decision.APPROVE,UUID.randomUUID());
        Envelope changed = new Envelope(valid.approvalId(),Decision.REJECT,valid.nonce(),
            valid.issuedAt(),valid.expiresAt(),valid.signature());
        assertThatThrownBy(() -> submitFixture(reopen(NOW),request(),pending,changed))
            .hasMessage("INVALID_INDEPENDENT_PROOF");
        assertThat(journal.count()).isZero();
    }

    private record Contention(AtomicLong now, AtomicReference<CurrentReview> review,
                              AtomicReference<Set<String>> grant,
                              AtomicReference<Optional<UserAccount>> account,
                              MockHttpServletRequest request) {}

    private String submitAfterLockWait(Consumer<Contention> change) throws Exception {
        var clock = mock(Clock.class);
        var now = new AtomicLong(NOW);
        when(clock.instant()).thenAnswer(invocation -> Instant.ofEpochSecond(now.get()));
        var current = new AtomicReference<>(new CurrentReview(pending,GateState.PASS));
        var grant = new AtomicReference<>(Set.of(SCOPE));
        var account = new AtomicReference<>(Optional.of(
            new UserAccount(OWNER,"owner","Synthetic owner","unused-test-hash",false,true)));
        var enteringJournal = new CountDownLatch(1);
        when(users.findById(OWNER)).thenAnswer(invocation -> account.get());
        when(grants.grantedScopes(OWNER,CLIENT)).thenAnswer(invocation -> grant.get());
        var req = request();
        var delegate = new StagingReleaseDecisionJournal(suffix);
        DecisionJournal observed = (reviewed, envelope, recheck) -> {
            // Initial identity, session, expiry and signature checks are complete.
            enteringJournal.countDown();
            delegate.record(reviewed,envelope,recheck);
        };
        var boundary = new StagingReleaseApprovalBoundary(users,grants,OWNER,keys.getPublic(),
            clock,observed);
        Envelope e = proof(pending,Decision.APPROVE,UUID.randomUUID());
        try (var pool = Executors.newSingleThreadExecutor()) {
            java.util.concurrent.Future<String> future;
            try (var lock = journal.holdLockForTest()) {
                future = pool.submit(() -> {
                    try { return boundary.submit(req,pending,e,current::get).state(); }
                    catch (IllegalArgumentException denied) { return denied.getMessage(); }
                });
                try {
                    assertThat(enteringJournal.await(3,TimeUnit.SECONDS)).isTrue();
                    // The journal cannot write while this independent transaction holds its row.
                    change.accept(new Contention(now,current,grant,account,req));
                } finally { lock.rollback(); }
            }
            return future.get(8,TimeUnit.SECONDS);
        }
    }

    @Test void expiredProofWhileWaitingForLockCannotCommit() throws Exception {
        assertThat(submitAfterLockWait(c -> c.now().set(NOW+30)))
            .isEqualTo("PROOF_EXPIRED_OR_FUTURE");
        assertThat(journal.count()).isZero();
    }

    @Test void revokedGrantWhileWaitingForLockCannotCommit() throws Exception {
        assertThat(submitAfterLockWait(c -> c.grant().set(Set.of())))
            .isEqualTo("REVIEW_GRANT_REVOKED");
        assertThat(journal.count()).isZero();
    }

    @Test void disabledAccountWhileWaitingForLockCannotCommit() throws Exception {
        assertThat(submitAfterLockWait(c -> c.account().set(Optional.empty())))
            .isEqualTo("ACCOUNT_UNAVAILABLE");
        assertThat(journal.count()).isZero();
    }

    @Test void changedCandidateWhileWaitingForLockCannotCommit() throws Exception {
        assertThat(submitAfterLockWait(c -> c.review().set(new CurrentReview(
            new Pending(pending.approvalId(),OWNER,SESSION,pending.commit(),
                pending.artifactDigest(),pending.schema(),pending.ciRun(),2,
                pending.evidenceDigest(),pending.createdAt(),pending.expiresAt()),GateState.PASS))))
            .isEqualTo("CURRENT_REVIEW_CHANGED");
        assertThat(journal.count()).isZero();
    }

    @Test void blockedGatesWhileWaitingForLockCannotCommit() throws Exception {
        assertThat(submitAfterLockWait(c -> c.review().set(new CurrentReview(pending,GateState.BLOCKED))))
            .isEqualTo("CURRENT_GATES_NOT_PASS");
        assertThat(journal.count()).isZero();
    }

    @Test void missingCurrentEvidenceWhileWaitingForLockCannotCommit() throws Exception {
        assertThat(submitAfterLockWait(c -> c.review().set(null)))
            .isEqualTo("CURRENT_GATES_NOT_PASS");
        assertThat(journal.count()).isZero();
    }

    @Test void changedSessionWhileWaitingForLockCannotCommit() throws Exception {
        assertThat(submitAfterLockWait(c -> c.request().setAttribute(SESSION_ATTRIBUTE,
            new VerifiedSession("sha256:"+"9".repeat(64)))))
            .isEqualTo("VERIFIED_SESSION_MISMATCH");
        assertThat(journal.count()).isZero();
    }

    @Test void unchangedReviewAfterLockWaitCommitsOneNonDispatchReceipt() throws Exception {
        assertThat(submitAfterLockWait(c -> c.now().set(NOW+1)))
            .isEqualTo("REVIEW_RECORDED_ONLY");
        assertThat(journal.count()).isEqualTo(1);
    }
}
