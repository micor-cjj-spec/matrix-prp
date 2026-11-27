package com.matrix.prp;

import static com.matrix.prp.ontology.PersonalOntology.NodeType.LITERAL;
import static com.matrix.prp.ontology.PersonalOntology.NodeType.PERSON;
import static com.matrix.prp.ontology.PersonalOntology.Relation.DECLARES_SKILL;
import static com.matrix.prp.ontology.PersonalOntology.Relation.HAS_BACKGROUND;
import static com.matrix.prp.ontology.PersonalOntology.Relation.PREFERS;
import static com.matrix.prp.ontology.PersonalOntology.Sensitivity.RESTRICTED;
import static com.matrix.prp.ontology.PersonalOntology.Sensitivity.NORMAL;
import static com.matrix.prp.ontology.PersonalOntologyAssertionGuard.EvidenceSource.CHAT_MESSAGE;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.assertThat;

import com.matrix.prp.ai.AiStore;
import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.memory.PersonalMemoryService;
import com.matrix.prp.goals.GoalService;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;

/**
 * Disposable CI MySQL 8.4 integration: verifies actual Spring transactions
 * serialize two distinct-key AI writes and competing confirmations. Not a mock.
 * Never uses production data; all fixtures have unique synthetic owners.
 */
@SpringBootTest
@ActiveProfiles("video-integration")
class PersonalOsAiConcurrencyDatabaseIT {
    @Autowired UserStore users;
    @Autowired AiStore chats;
    @Autowired JdbcTemplate jdbc;
    @Autowired PersonalMemoryService memories;
    @Autowired GoalService goals;
    @Autowired PlatformTransactionManager transactions;

    private static String key(String prefix) {
        return prefix + UUID.randomUUID().toString().replace("-", "").substring(0, 20);
    }

    private void as(UserAccount account) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(account.profile(), null, List.of()));
    }

    private List<Long> race(UserAccount owner, Callable<Long> first, Callable<Long> second)
            throws Exception {
        ExecutorService pool=Executors.newFixedThreadPool(2);
        CountDownLatch ready=new CountDownLatch(2);
        CountDownLatch start=new CountDownLatch(1);
        try {
            List<Future<Long>> jobs=new ArrayList<>();
            for (Callable<Long> action:List.of(first,second)) {
                jobs.add(pool.submit(() -> {
                    as(owner);
                    try {
                        ready.countDown();
                        if (!start.await(15,TimeUnit.SECONDS))
                            throw new IllegalStateException("Synthetic CI race did not start");
                        try {
                            return action.call();
                        } catch (ResponseStatusException expected) {
                            if (expected.getStatusCode()!=HttpStatus.CONFLICT) throw expected;
                            return -409L;
                        }
                    } finally {
                        SecurityContextHolder.clearContext();
                    }
                }));
            }
            assertThat(ready.await(15,TimeUnit.SECONDS)).isTrue();
            start.countDown();
            return List.of(jobs.get(0).get(40,TimeUnit.SECONDS),
                jobs.get(1).get(40,TimeUnit.SECONDS));
        } finally {
            start.countDown();
            pool.shutdownNow();
            assertThat(pool.awaitTermination(15,TimeUnit.SECONDS)).isTrue();
        }
    }

    // Establish both consistent snapshots before either request can insert.
    // GoalService joins these actual REPEATABLE READ transactions through AOP.
    private long createFromMissingSnapshot(long owner, GoalService.Create request,
                                           CountDownLatch snapshots) {
        var transaction = new TransactionTemplate(transactions);
        transaction.setIsolationLevel(TransactionDefinition.ISOLATION_REPEATABLE_READ);
        return transaction.execute(status -> {
            assertThat(jdbc.queryForObject(
                "SELECT COUNT(*) FROM prp_goals WHERE user_id=? AND request_key=?",
                Integer.class, owner, request.requestKey())).isZero();
            snapshots.countDown();
            try {
                if (!snapshots.await(15, TimeUnit.SECONDS))
                    throw new IllegalStateException("Both goal snapshots must precede insert");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Goal race interrupted", e);
            }
            return goals.create(request).id();
        });
    }

    @Test void concurrentGoalRetriesReturnWinnerOrPayloadConflict() throws Exception {
        String database=jdbc.execute((ConnectionCallback<String>) connection ->
            connection.getMetaData().getURL());
        if (!"true".equals(System.getenv("GITHUB_ACTIONS"))
                || !"Linux".equals(System.getenv("RUNNER_OS"))
                || database==null || !database.matches(
                    "jdbc:mysql://(localhost|127\\.0\\.0\\.1):3306/matrix_prp(\\?.*)?"))
            throw new SecurityException("DISPOSABLE_PERSONAL_OS_GOAL_MYSQL_ONLY");

        UserAccount owner=users.create(key("goal_ci_"),"Synthetic Goal Owner",
            "CI-only-irrelevant-password-hash",false);
        long id=owner.id();
        try {
            String identicalKey=key("goal_same_");
            var same=new GoalService.Create("Synthetic same goal",null,"career",
                "medium",null,null,identicalKey);
            var sameSnapshots=new CountDownLatch(2);
            var identical=race(owner,
                ()->createFromMissingSnapshot(id,same,sameSnapshots),
                ()->createFromMissingSnapshot(id,same,sameSnapshots));
            assertThat(identical.get(0)).isPositive();
            assertThat(identical.get(1)).isEqualTo(identical.get(0));
            assertThat(jdbc.queryForObject(
                "SELECT COUNT(*) FROM prp_goals WHERE user_id=? AND request_key=?",
                Integer.class,id,identicalKey)).isEqualTo(1);

            String conflictKey=key("goal_conflict_");
            var first=new GoalService.Create("Synthetic first goal",null,"career",
                "medium",null,null,conflictKey);
            var second=new GoalService.Create("Synthetic conflicting goal",null,"career",
                "medium",null,null,conflictKey);
            var conflictSnapshots=new CountDownLatch(2);
            var conflicting=race(owner,
                ()->createFromMissingSnapshot(id,first,conflictSnapshots),
                ()->createFromMissingSnapshot(id,second,conflictSnapshots));
            assertThat(conflicting).contains(-409L);
            assertThat(conflicting.stream().filter(n->n>0).count()).isEqualTo(1);
            assertThat(jdbc.queryForObject(
                "SELECT COUNT(*) FROM prp_goals WHERE user_id=? AND request_key=?",
                Integer.class,id,conflictKey)).isEqualTo(1);
        } finally {
            SecurityContextHolder.clearContext();
            jdbc.update("DELETE FROM prp_goals WHERE user_id=?",id);
            jdbc.update("DELETE FROM prp_users WHERE id=?",id);
        }
    }

    private long seedPending(long owner,String text,String key) {
        jdbc.update("""
            INSERT INTO prp_personal_assertions
            (user_id,subject_type,subject_ref,predicate,object_type,object_value,
             source_type,origin,status,sensitivity,request_key,created_at,updated_at)
            VALUES (?,'PERSON',?,'DECLARES_SKILL','LITERAL',?,
              'USER_INPUT','AI_CANDIDATE','PENDING','RESTRICTED',?,NOW(6),NOW(6))
            """,owner,Long.toString(owner),text,key);
        return jdbc.queryForObject("""
            SELECT id FROM prp_personal_assertions WHERE user_id=? AND request_key=?
            """,Long.class,owner,key);
    }

    /**
     * T-007 U06/U07: disposable real MySQL conversation/source revocation and
     * two independent synthetic principals. Never touches an existing account.
     * Not a substitute for two-session browser/provider manual acceptance.
     */
    @Test void revokedChatEvidenceRemainsManageableButNeverModelVisible()
            throws Exception {
        String database=jdbc.execute((ConnectionCallback<String>) connection ->
            connection.getMetaData().getURL());
        if (!"true".equals(System.getenv("GITHUB_ACTIONS"))
                || !"Linux".equals(System.getenv("RUNNER_OS"))
                || database==null || !database.matches(
                    "jdbc:mysql://(localhost|127\\.0\\.0\\.1):3306/matrix_prp(\\?.*)?"))
            throw new SecurityException("DISPOSABLE_PERSONAL_OS_SOURCE_MYSQL_ONLY");

        UserAccount owner=users.create(key("src_owner_"),"Synthetic Source Owner",
            "CI-only-irrelevant-password-hash",false);
        UserAccount other=users.create(key("src_other_"),"Synthetic Foreign Owner",
            "CI-only-irrelevant-password-hash",false);
        var chat=chats.create(owner.id(),"Synthetic chat source");
        String quote="I prefer concise checklists";
        long messageId=chats.append(owner.id(),chat.id(),"user",
            "Synthetic user source: "+quote+" for learning.");
        try {
            as(owner);
            var manual=memories.propose(new PersonalMemoryService.Proposed(
                PERSON,Long.toString(owner.id()),PREFERS,LITERAL,null,
                "CI-only personal preference backed by chat",CHAT_MESSAGE,
                Long.toString(messageId),null,null,NORMAL,key("normal_src_")));
            var confirmed=memories.confirm(manual.id());
            assertThat(memories.listCurrent())
                .extracting(PersonalMemoryService.Memory::id).contains(confirmed.id());
            assertThat(memories.sourcePreview(confirmed.id()).messageId())
                .isEqualTo(messageId);
            var pending=memories.proposeAiCandidate(new PersonalMemoryService.AiCandidate(
                HAS_BACKGROUND,"CI-only pending sourced background",null,null,
                RESTRICTED,key("candidate_src_"),messageId,quote));
            assertThat(pending.status()).isEqualTo("PENDING");
            assertThat(pending.sourceType()).isEqualTo(CHAT_MESSAGE);

            as(other);
            assertThat(memories.listCurrent()).isEmpty();
            assertThat(memories.listNormalHistory()).isEmpty();
            assertThat(memories.pending()).isEmpty();
            assertThatThrownBy(() -> memories.get(confirmed.id()))
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(e -> assertThat(((ResponseStatusException)e).getStatusCode())
                    .isEqualTo(HttpStatus.NOT_FOUND));
            assertThatThrownBy(() -> memories.sourcePreview(confirmed.id()))
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(e -> assertThat(((ResponseStatusException)e).getStatusCode())
                    .isEqualTo(HttpStatus.NOT_FOUND));
            assertThatThrownBy(() -> memories.proposeAiCandidate(
                new PersonalMemoryService.AiCandidate(HAS_BACKGROUND,
                    "CI-only foreign sourced attempt",null,null,RESTRICTED,
                    key("foreign_src_"),messageId,quote)))
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(e -> assertThat(((ResponseStatusException)e).getStatusCode())
                    .isEqualTo(HttpStatus.NOT_FOUND));

            as(owner);
            chats.softDelete(owner.id(),chat.id());
            assertThat(memories.listCurrent())
                .extracting(PersonalMemoryService.Memory::id)
                .doesNotContain(confirmed.id());
            assertThat(memories.listNormalHistory())
                .extracting(PersonalMemoryService.Memory::id).contains(confirmed.id());
            assertThat(memories.pending())
                .extracting(PersonalMemoryService.Memory::id).contains(pending.id());
            assertThatThrownBy(() -> memories.sourcePreview(confirmed.id()))
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(e -> assertThat(((ResponseStatusException)e).getStatusCode())
                    .isEqualTo(HttpStatus.NOT_FOUND));
            assertThatThrownBy(() -> memories.confirm(pending.id()))
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(e -> assertThat(((ResponseStatusException)e).getStatusCode())
                    .isEqualTo(HttpStatus.NOT_FOUND));

            memories.erase(pending.id());
            memories.erase(confirmed.id());
            assertThat(memories.listNormalHistory())
                .extracting(PersonalMemoryService.Memory::id)
                .doesNotContain(confirmed.id());
            assertThat(memories.pending())
                .extracting(PersonalMemoryService.Memory::id)
                .doesNotContain(pending.id());
        } finally {
            SecurityContextHolder.clearContext();
            jdbc.update("DELETE FROM prp_personal_assertions WHERE user_id IN (?,?)",
                owner.id(),other.id());
            jdbc.update("DELETE FROM prp_ai_messages WHERE conversation_id=?",chat.id());
            jdbc.update("DELETE FROM prp_ai_conversation_meta WHERE conversation_id=?",chat.id());
            jdbc.update("DELETE FROM prp_ai_conversations WHERE id=? AND user_id=?",
                chat.id(),owner.id());
            jdbc.update("DELETE FROM prp_users WHERE id IN (?,?)",owner.id(),other.id());
        }
    }

    @Test void concurrentDistinctKeysAndCompetingConfirmationsCannotBothWin()
            throws Exception {
        // The test mutates and deletes synthetic users; never run against a
        // developer or production MySQL even when pointed to a PRP database.
        String database=jdbc.execute((ConnectionCallback<String>) connection ->
            connection.getMetaData().getURL());
        if (!"true".equals(System.getenv("GITHUB_ACTIONS"))
                || !"Linux".equals(System.getenv("RUNNER_OS"))
                || database==null || !database.matches(
                    "jdbc:mysql://(localhost|127\\.0\\.0\\.1):3306/matrix_prp(\\?.*)?")) {
            throw new SecurityException("DISPOSABLE_PERSONAL_OS_CONCURRENCY_MYSQL_ONLY");
        }
        UserAccount owner=users.create(key("pos_ai_ci_"),"Synthetic Personal OS",
            "CI-only-irrelevant-password-hash",false);
        long id=owner.id();
        try {
            String k1=key("source_a_"),k2=key("source_b_");
            var outcomes=race(owner,
                ()->memories.proposeAiCandidate(new PersonalMemoryService.AiCandidate(
                    DECLARES_SKILL,"Synthetic Concurrent Java",null,null,RESTRICTED,k1)).id(),
                ()->memories.proposeAiCandidate(new PersonalMemoryService.AiCandidate(
                    DECLARES_SKILL,"SYNTHETIC CONCURRENT JAVA",null,null,RESTRICTED,k2)).id());
            assertThat(outcomes).contains(-409L);
            assertThat(outcomes.stream().filter(n->n>0).count()).isEqualTo(1);
            assertThat(jdbc.queryForObject("""
                SELECT COUNT(*) FROM prp_personal_assertions
                WHERE user_id=? AND origin='AI_CANDIDATE' AND status='PENDING'
                """,Integer.class,id)).isEqualTo(1);

            as(owner);
            long pending=outcomes.stream().filter(n->n>0).findFirst().orElseThrow();
            memories.invalidate(pending);
            SecurityContextHolder.clearContext();

            // Simulate two legacy PENDING proposals written before dedup existed.
            long first=seedPending(id,"Synthetic Historical Skill",key("historic_a_"));
            long second=seedPending(id,"synthetic historical skill",key("historic_b_"));
            var confirmations=race(owner,
                ()->memories.confirm(first).id(),
                ()->memories.confirm(second).id());
            assertThat(confirmations).contains(-409L);
            assertThat(confirmations.stream().filter(n->n>0).count()).isEqualTo(1);
            assertThat(jdbc.queryForObject("""
                SELECT COUNT(*) FROM prp_personal_assertions
                WHERE user_id=? AND predicate='DECLARES_SKILL'
                  AND status='CONFIRMED' AND object_value LIKE '%Historical Skill%'
                """,Integer.class,id)).isEqualTo(1);
        } finally {
            SecurityContextHolder.clearContext();
            jdbc.update("DELETE FROM prp_personal_assertions WHERE user_id=?",id);
            jdbc.update("DELETE FROM prp_users WHERE id=?",id);
        }
    }
}
