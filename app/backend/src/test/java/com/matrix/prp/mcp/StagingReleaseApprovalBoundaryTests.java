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
import java.util.concurrent.Executors;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

import static com.matrix.prp.mcp.StagingReleaseApprovalBoundary.*;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

class StagingReleaseApprovalBoundaryTests {
    private static final long OWNER = 7;
    private static final long NOW = 1700000000L;
    private static final String SESSION = "sha256:" + "1".repeat(64);
    private static final String ARTIFACT = "sha256:" + "2".repeat(64);
    private static final String EVIDENCE = "sha256:" + "3".repeat(64);
    private final UserStore users = mock(UserStore.class);
    private final McpClientGrantService grants = mock(McpClientGrantService.class);
    private KeyPair signer;
    private StagingReleaseApprovalBoundary boundary;
    private Pending pending;
    private MockHttpServletRequest request;

    @BeforeEach
    void setup() throws Exception {
        signer = KeyPairGenerator.getInstance("Ed25519").generateKeyPair();
        boundary = new StagingReleaseApprovalBoundary(users,grants,OWNER,signer.getPublic(),
            Clock.fixed(Instant.ofEpochSecond(NOW), ZoneOffset.UTC));
        when(users.findById(OWNER)).thenReturn(Optional.of(account(true)));
        when(grants.grantedScopes(OWNER,CLIENT)).thenReturn(Set.of(SCOPE));
        pending = new Pending(UUID.randomUUID(),OWNER,SESSION,"a".repeat(40),ARTIFACT,
            30,123,1,EVIDENCE,NOW-30,NOW+300);
        request = authenticated(OWNER,CLIENT,true,true);
    }

    private UserAccount account(boolean enabled) {
        return new UserAccount(OWNER,"owner","Synthetic owner","unused-test-hash",false,enabled);
    }

    private MockHttpServletRequest authenticated(long id, String client, boolean tokenScope, boolean grantScope) {
        var auth = new UsernamePasswordAuthenticationToken(new UserProfile(id,"owner","Synthetic owner"),
            null,tokenScope ? List.of(new SimpleGrantedAuthority("SCOPE_"+SCOPE)) : List.of());
        auth.setDetails(new McpScopeGuard.VerifiedClient(client,grantScope?Set.of(SCOPE):Set.of()));
        var req = new MockHttpServletRequest();
        req.setAttribute(McpOAuthTransportConfiguration.VERIFIED_AUTH,auth);
        req.setAttribute(SESSION_ATTRIBUTE,new VerifiedSession(SESSION));
        return req;
    }

    private Envelope signed(Pending p, Decision decision, UUID nonce, long issued, long expires,
                            KeyPair key) throws Exception {
        var unsigned = new Envelope(p.approvalId(),decision,nonce,issued,expires,null);
        Signature signature = Signature.getInstance("Ed25519");
        signature.initSign(key.getPrivate());
        signature.update(signedBytes(p,unsigned));
        return new Envelope(p.approvalId(),decision,nonce,issued,expires,signature.sign());
    }

    private Envelope proof(Decision decision) throws Exception {
        return signed(pending,decision,UUID.randomUUID(),NOW-1,NOW+30,signer);
    }

    @Test void validIndependentProofProducesOnlyNonauthorizingReceipt() throws Exception {
        var receipt = submitFixture(boundary,request,pending,proof(Decision.APPROVE));
        assertThat(receipt.state()).isEqualTo("REVIEW_RECORDED_ONLY");
        assertThat(receipt.environment()).isEqualTo("prp-unified-396");
        assertThat(receipt.decision()).isEqualTo(Decision.APPROVE);
        assertThat(receipt.deploymentAuthorized() || receipt.productionAuthorized()
            || receipt.releaseEligible() || receipt.liveVerified()).isFalse();
    }

    @Test void reusedExistingVerifiedPrincipalCaptureFilter() throws Exception {
        var auth = (UsernamePasswordAuthenticationToken) request.getAttribute(
            McpOAuthTransportConfiguration.VERIFIED_AUTH);
        var captured = new MockHttpServletRequest();
        captured.setAttribute(SESSION_ATTRIBUTE,new VerifiedSession(SESSION));
        try {
            SecurityContextHolder.getContext().setAuthentication(auth);
            new McpVerifiedPrincipalCaptureFilter().doFilter(captured,
                new MockHttpServletResponse(),new MockFilterChain());
            assertThat(submitFixture(boundary,captured,pending,proof(Decision.APPROVE)).state())
                .isEqualTo("REVIEW_RECORDED_ONLY");
        } finally { SecurityContextHolder.clearContext(); }
    }

    @Test void headerCannotSubstituteForVerifiedTransportIdentity() throws Exception {
        var untrusted = new MockHttpServletRequest();
        untrusted.addHeader("Authorization","Bearer synthetic-unverified");
        untrusted.addHeader(McpOAuthTransportConfiguration.VERIFIED_AUTH,"owner");
        untrusted.addHeader(SESSION_ATTRIBUTE,SESSION);
        Envelope e = proof(Decision.APPROVE);
        assertThatThrownBy(() -> submitFixture(boundary,untrusted,pending,e))
            .hasMessage("VERIFIED_OAUTH_REQUIRED");
        verifyNoInteractions(users,grants);
    }

    @Test void firstPartyPrincipalWithoutVerifiedClientDenied() throws Exception {
        request.setAttribute(McpOAuthTransportConfiguration.VERIFIED_AUTH,
            new UsernamePasswordAuthenticationToken(new UserProfile(OWNER,"owner","Owner"),null,List.of()));
        Envelope e = proof(Decision.APPROVE);
        assertThatThrownBy(() -> submitFixture(boundary,request,pending,e)).hasMessage("VERIFIED_OAUTH_REQUIRED");
    }

    @Test void wrongOwnerAndWrongClientDenied() throws Exception {
        Envelope e = proof(Decision.APPROVE);
        assertThatThrownBy(() -> submitFixture(boundary,authenticated(99,CLIENT,true,true),pending,e))
            .hasMessage("RELEASE_OWNER_REQUIRED");
        assertThatThrownBy(() -> submitFixture(boundary,authenticated(OWNER,"other-client",true,true),pending,e))
            .hasMessage("REVIEW_SCOPE_REQUIRED");
    }

    @Test void bothTokenScopeAndOwnerGrantRequired() throws Exception {
        Envelope e = proof(Decision.APPROVE);
        for (var req : List.of(authenticated(OWNER,CLIENT,false,true),authenticated(OWNER,CLIENT,true,false))) {
            assertThatThrownBy(() -> submitFixture(boundary,req,pending,e)).hasMessage("REVIEW_SCOPE_REQUIRED");
        }
        when(grants.grantedScopes(OWNER,CLIENT)).thenReturn(Set.of());
        assertThatThrownBy(() -> submitFixture(boundary,request,pending,e)).hasMessage("REVIEW_GRANT_REVOKED");
    }

    @Test void disabledAccountDeniedEvenWithCapturedAuthentication() throws Exception {
        when(users.findById(OWNER)).thenReturn(Optional.of(account(false)));
        Envelope e = proof(Decision.APPROVE);
        assertThatThrownBy(() -> submitFixture(boundary,request,pending,e)).hasMessage("ACCOUNT_UNAVAILABLE");
    }

    @Test void missingWrongOrUntrustedSessionDenied() throws Exception {
        Envelope e = proof(Decision.APPROVE);
        request.removeAttribute(SESSION_ATTRIBUTE);
        request.addHeader(SESSION_ATTRIBUTE,SESSION);
        assertThatThrownBy(() -> submitFixture(boundary,request,pending,e)).hasMessage("VERIFIED_SESSION_MISMATCH");
        request.setAttribute(SESSION_ATTRIBUTE,SESSION);
        assertThatThrownBy(() -> submitFixture(boundary,request,pending,e)).hasMessage("VERIFIED_SESSION_MISMATCH");
        request.setAttribute(SESSION_ATTRIBUTE,new VerifiedSession("sha256:"+"9".repeat(64)));
        assertThatThrownBy(() -> submitFixture(boundary,request,pending,e)).hasMessage("VERIFIED_SESSION_MISMATCH");
    }

    @Test void attackerSignatureOrUnsignedClickDenied() throws Exception {
        var forged = signed(pending,Decision.APPROVE,UUID.randomUUID(),NOW-1,NOW+30,
            KeyPairGenerator.getInstance("Ed25519").generateKeyPair());
        assertThatThrownBy(() -> submitFixture(boundary,request,pending,forged)).hasMessage("INVALID_INDEPENDENT_PROOF");
        var unsigned = new Envelope(pending.approvalId(),Decision.APPROVE,UUID.randomUUID(),NOW-1,NOW+30,null);
        assertThatThrownBy(() -> submitFixture(boundary,request,pending,unsigned)).hasMessage("INVALID_INDEPENDENT_PROOF");
    }

    @Test void signatureBindsDecisionAndNonce() throws Exception {
        Envelope e = proof(Decision.APPROVE);
        var changed = new Envelope(e.approvalId(),Decision.REJECT,e.nonce(),e.issuedAt(),e.expiresAt(),e.signature());
        var nonce = new Envelope(e.approvalId(),e.decision(),UUID.randomUUID(),e.issuedAt(),e.expiresAt(),e.signature());
        assertThatThrownBy(() -> submitFixture(boundary,request,pending,changed)).hasMessage("INVALID_INDEPENDENT_PROOF");
        assertThatThrownBy(() -> submitFixture(boundary,request,pending,nonce)).hasMessage("INVALID_INDEPENDENT_PROOF");
    }

    @Test void changedCandidateArtifactSchemaAttemptOrEvidenceDenied() throws Exception {
        Envelope e = proof(Decision.APPROVE);
        List<Pending> changes = List.of(
            changed("b".repeat(40),ARTIFACT,30,1,EVIDENCE),
            changed(pending.commit(),"sha256:"+"8".repeat(64),30,1,EVIDENCE),
            changed(pending.commit(),ARTIFACT,31,1,EVIDENCE),
            changed(pending.commit(),ARTIFACT,30,2,EVIDENCE),
            changed(pending.commit(),ARTIFACT,30,1,"sha256:"+"8".repeat(64)));
        for (Pending next : changes) {
            assertThatThrownBy(() -> submitFixture(boundary,request,next,e)).hasMessage("INVALID_INDEPENDENT_PROOF");
        }
    }

    private Pending changed(String commit,String artifact,int schema,int attempt,String evidence) {
        return new Pending(pending.approvalId(),OWNER,SESSION,commit,artifact,schema,
            pending.ciRun(),attempt,evidence,pending.createdAt(),pending.expiresAt());
    }

    @Test void proofExpiryFutureIssuanceAndLongLifetimeDenied() throws Exception {
        for (Envelope e : List.of(
            signed(pending,Decision.APPROVE,UUID.randomUUID(),NOW-20,NOW,signer),
            signed(pending,Decision.APPROVE,UUID.randomUUID(),NOW+1,NOW+30,signer),
            signed(pending,Decision.APPROVE,UUID.randomUUID(),NOW-1,NOW+61,signer))) {
            assertThatThrownBy(() -> submitFixture(boundary,request,pending,e)).hasMessage("PROOF_EXPIRED_OR_FUTURE");
        }
    }

    @Test void expiredPendingDenied() throws Exception {
        var old = new Pending(pending.approvalId(),OWNER,SESSION,pending.commit(),ARTIFACT,
            30,123,1,EVIDENCE,NOW-100,NOW);
        Envelope e = proof(Decision.APPROVE);
        assertThatThrownBy(() -> submitFixture(boundary,request,old,e)).hasMessage("PENDING_EXPIRED_OR_FUTURE");
    }

    @Test void replayAndOppositeDecisionDeniedAfterSuccess() throws Exception {
        Envelope e = proof(Decision.APPROVE);
        submitFixture(boundary,request,pending,e);
        assertThatThrownBy(() -> submitFixture(boundary,request,pending,e)).hasMessage("REPLAY_OR_ALREADY_DECIDED");
        Envelope other = proof(Decision.REJECT);
        assertThatThrownBy(() -> submitFixture(boundary,request,pending,other)).hasMessage("REPLAY_OR_ALREADY_DECIDED");
    }

    @Test void sameNonceCannotBeReusedAcrossApprovalIds() throws Exception {
        Envelope e = proof(Decision.APPROVE);
        submitFixture(boundary,request,pending,e);
        var second = new Pending(UUID.randomUUID(),OWNER,SESSION,"b".repeat(40),ARTIFACT,
            30,123,1,EVIDENCE,NOW-30,NOW+300);
        Envelope replay = signed(second,Decision.APPROVE,e.nonce(),NOW-1,NOW+30,signer);
        assertThatThrownBy(() -> submitFixture(boundary,request,second,replay)).hasMessage("REPLAY_OR_ALREADY_DECIDED");
    }

    @Test void concurrentOpposingDecisionsProduceOneReceipt() throws Exception {
        Envelope approve = proof(Decision.APPROVE), reject = proof(Decision.REJECT);
        try (var pool = Executors.newFixedThreadPool(2)) {
            Callable<String> a = () -> outcome(approve);
            Callable<String> b = () -> outcome(reject);
            var results = pool.invokeAll(List.of(a,b));
            assertThat(List.of(results.get(0).get(),results.get(1).get()))
                .containsExactlyInAnyOrder("REVIEW_RECORDED_ONLY","REPLAY_OR_ALREADY_DECIDED");
        }
    }

    private Receipt submitFixture(StagingReleaseApprovalBoundary b,
                                  MockHttpServletRequest req, Pending reviewed, Envelope e) {
        return b.submit(req, reviewed, e, () -> new CurrentReview(reviewed, GateState.PASS));
    }

    private String outcome(Envelope e) {
        try { return submitFixture(boundary,request,pending,e).state(); }
        catch (IllegalArgumentException denied) { return denied.getMessage(); }
    }

    @Test void rejectAlsoReturnsNoExecutionAuthority() throws Exception {
        Receipt receipt = submitFixture(boundary,request,pending,proof(Decision.REJECT));
        assertThat(receipt.decision()).isEqualTo(Decision.REJECT);
        assertThat(receipt.productionAuthorized()).isFalse();
        assertThat(receipt.deploymentAuthorized()).isFalse();
    }
}
