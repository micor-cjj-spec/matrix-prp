package com.matrix.prp;

import static com.matrix.prp.ontology.PersonalOntology.NodeType.*;
import static com.matrix.prp.ontology.PersonalOntology.Relation.*;
import static com.matrix.prp.ontology.PersonalOntology.Sensitivity.*;
import static com.matrix.prp.ontology.PersonalOntologyAssertionGuard.EvidenceSource.USER_INPUT;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.goals.GoalService;
import com.matrix.prp.memory.PersonalMemoryService;
import com.matrix.prp.ontology.PersonalOntologyReferenceGuard;
import java.sql.Connection;
import java.time.LocalDateTime;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.SingleConnectionDataSource;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;

/**
 * Service-level lifecycle proof against disposable Flyway CI MySQL V31.
 * Caller owns a single uncommitted JDBC connection and always rolls it back.
 * This tests real SQL and authorization, not Spring AOP concurrency/atomicity.
 */
final class PersonalOsServiceLifecycleChecks {
    private PersonalOsServiceLifecycleChecks() {}

    static void verify(Connection connection, long otherGoal, long ownedRecord) {
        JdbcTemplate db = new JdbcTemplate(new SingleConnectionDataSource(connection, true));
        PersonalOntologyReferenceGuard references = new PersonalOntologyReferenceGuard(db);
        GoalService goals = new GoalService(db, references);
        PersonalMemoryService memories = new PersonalMemoryService(db, references);
        try {
            authenticate(970001, "personal_os_ci_a");

            GoalService.Create request = new GoalService.Create(
                "Synthetic Personal OS goal", "Synthetic only", "career",
                "medium", "One deterministic milestone", null, "pos_goal_create_0001");
            GoalService.Goal goal = goals.create(request);
            assertThat(goal.id()).isPositive();
            assertThat(goal.status()).isEqualTo("PLANNED");
            assertThat(goals.create(request).id()).isEqualTo(goal.id());
            assertHttp(HttpStatus.CONFLICT,
                () -> goals.create(new GoalService.Create(
                    "Different goal", request.description(), request.domain(),
                    request.priority(), request.successCriteria(), null, request.requestKey())));
            assertThat(goals.list()).extracting(GoalService.Goal::id).contains(goal.id());
            assertHttp(HttpStatus.NOT_FOUND, () -> goals.get(otherGoal));

            // Same-row optimistic updates require the exact server revision.
            assertHttp(HttpStatus.CONFLICT, () -> goals.revise(goal.id(),
                new GoalService.Revision("Bad revision", null, "career", "medium",
                    null, null, LocalDateTime.of(2020,1,1,0,0))));
            GoalService.Goal revised = goals.revise(goal.id(),
                new GoalService.Revision("Updated synthetic goal", "Synthetic only",
                    "career", "high", "One deterministic milestone", null,
                    goal.updatedAt()));
            assertThat(revised.title()).isEqualTo("Updated synthetic goal");
            assertThat(revised.priority()).isEqualTo("high");

            // Unclassified personal details are RESTRICTED by default, even after confirmation.
            PersonalMemoryService.Proposed restrictedRequest = new PersonalMemoryService.Proposed(
                PERSON, "970001", HAS_BACKGROUND, LITERAL, null, "Synthetic restricted statement",
                USER_INPUT, null, null, null, null, "pos_memory_private_001");
            var restricted = memories.propose(restrictedRequest);
            assertThat(restricted.status()).isEqualTo("PENDING");
            assertThat(restricted.sensitivity()).isEqualTo("RESTRICTED");
            assertThat(memories.listCurrent()).extracting(PersonalMemoryService.Memory::id)
                .doesNotContain(restricted.id());
            memories.confirm(restricted.id());
            assertThat(memories.listCurrent()).extracting(PersonalMemoryService.Memory::id)
                .doesNotContain(restricted.id());
            assertThat(memories.listPrivate()).extracting(PersonalMemoryService.Memory::id)
                .contains(restricted.id());

            PersonalMemoryService.Proposed initial = new PersonalMemoryService.Proposed(
                PERSON, "970001", DECLARES_SKILL, LITERAL, null, "Synthetic Java skill",
                USER_INPUT, null, null, null, NORMAL, "pos_memory_normal_001");
            var first = memories.propose(initial);
            assertThat(memories.pending()).extracting(PersonalMemoryService.Memory::id)
                .contains(first.id());
            assertThat(memories.listCurrent()).extracting(PersonalMemoryService.Memory::id)
                .doesNotContain(first.id());
            assertThat(memories.propose(initial).id()).isEqualTo(first.id());
            assertHttp(HttpStatus.CONFLICT, () -> memories.propose(
                new PersonalMemoryService.Proposed(PERSON, "970001", DECLARES_SKILL,
                    LITERAL, null, "Different payload", USER_INPUT, null, null, null,
                    NORMAL, "pos_memory_normal_001")));
            assertThat(memories.confirm(first.id()).status()).isEqualTo("CONFIRMED");
            assertThat(memories.propose(initial).id()).isEqualTo(first.id());
            assertThat(memories.listCurrent()).extracting(PersonalMemoryService.Memory::id)
                .contains(first.id());
            assertThat(memories.listPrivate()).extracting(PersonalMemoryService.Memory::id)
                .doesNotContain(first.id());

            // Revision must preserve subject+predicate, and is not live until confirmed.
            var revision = memories.proposeReplacement(first.id(),
                new PersonalMemoryService.Proposed(
                    PERSON, "970001", DECLARES_SKILL, LITERAL, null, "Synthetic upgraded skill",
                    USER_INPUT, null, null, null, NORMAL, "pos_memory_revised_001"));
            assertThat(revision.supersedesId()).isEqualTo(first.id());
            assertThat(memories.get(first.id()).status()).isEqualTo("CONFIRMED");
            assertThat(memories.confirm(revision.id()).status()).isEqualTo("CONFIRMED");
            assertThat(memories.get(first.id()).status()).isEqualTo("SUPERSEDED");
            assertThat(memories.listCurrent()).extracting(PersonalMemoryService.Memory::id)
                .contains(revision.id()).doesNotContain(first.id());
            assertHttp(HttpStatus.CONFLICT, () -> memories.confirm(first.id()));
            assertHttp(HttpStatus.BAD_REQUEST, () -> memories.proposeReplacement(revision.id(),
                new PersonalMemoryService.Proposed(
                    PERSON, "970001", PREFERS, LITERAL, null, "Mismatch",
                    USER_INPUT, null, null, null, NORMAL, "pos_memory_wrong_001")));

            // Source revocation must hide facts, even if the DB status remains CONFIRMED.
            var sourced = memories.propose(new PersonalMemoryService.Proposed(
                PERSON, "970001", HAS_EVENT_RECORD, RECORD, Long.toString(ownedRecord),
                null, com.matrix.prp.ontology.PersonalOntologyAssertionGuard.EvidenceSource.RECORD,
                Long.toString(ownedRecord), null, null, NORMAL, "pos_memory_record_001"));
            memories.confirm(sourced.id());
            var stalePrivate = memories.propose(new PersonalMemoryService.Proposed(
                PERSON, "970001", HAS_EVENT_RECORD, RECORD, Long.toString(ownedRecord),
                null, com.matrix.prp.ontology.PersonalOntologyAssertionGuard.EvidenceSource.RECORD,
                Long.toString(ownedRecord), null, null, RESTRICTED, "pos_private_source_001"));
            memories.confirm(stalePrivate.id());
            var stalePending = memories.propose(new PersonalMemoryService.Proposed(
                PERSON, "970001", HAS_EVENT_RECORD, RECORD, Long.toString(ownedRecord),
                null, com.matrix.prp.ontology.PersonalOntologyAssertionGuard.EvidenceSource.RECORD,
                Long.toString(ownedRecord), null, null, RESTRICTED, "pos_pending_source_001"));
            assertThat(memories.listCurrent()).extracting(PersonalMemoryService.Memory::id)
                .contains(sourced.id());
            assertThat(db.update("UPDATE prp_records SET deleted=1 WHERE id=? AND user_id=?",
                ownedRecord, 970001L)).isEqualTo(1);
            assertThat(memories.listCurrent()).extracting(PersonalMemoryService.Memory::id)
                .doesNotContain(sourced.id());
            assertThat(memories.listPrivate()).extracting(PersonalMemoryService.Memory::id)
                .contains(stalePrivate.id());
            assertThat(memories.pending()).extracting(PersonalMemoryService.Memory::id)
                .contains(stalePending.id());
            assertHttp(HttpStatus.NOT_FOUND, () -> memories.confirm(stalePending.id()));
            memories.invalidate(stalePrivate.id());
            assertThat(memories.listPrivate()).extracting(PersonalMemoryService.Memory::id)
                .contains(stalePrivate.id());
            assertThat(memories.listCurrent()).extracting(PersonalMemoryService.Memory::id)
                .doesNotContain(stalePrivate.id());
            memories.erase(stalePending.id());
            memories.erase(stalePrivate.id());
            assertHttp(HttpStatus.NOT_FOUND, () -> memories.get(stalePrivate.id()));

            // A confirmed relation becomes invalid when its goal is deleted.
            var relation = memories.propose(new PersonalMemoryService.Proposed(
                PERSON, "970001", PURSUES, GOAL, Long.toString(goal.id()), null,
                USER_INPUT, null, null, null, NORMAL, "pos_memory_goal_001"));
            memories.confirm(relation.id());
            assertThat(goals.context(goal.id())).extracting(GoalService.Link::assertionId)
                .contains(relation.id());
            goals.changeStatus(goal.id(), "ACTIVE");
            goals.changeStatus(goal.id(), "COMPLETED");
            assertHttp(HttpStatus.CONFLICT, () -> goals.changeStatus(goal.id(), "ACTIVE"));
            goals.delete(goal.id());
            assertThat(memories.get(relation.id()).status()).isEqualTo("INVALID");
            assertThat(memories.listCurrent()).extracting(PersonalMemoryService.Memory::id)
                .doesNotContain(relation.id());
            assertHttp(HttpStatus.NOT_FOUND, () -> goals.get(goal.id()));

            // Hard erasure detaches reverse links without leaving old literal values.
            memories.erase(first.id());
            assertThat(memories.get(revision.id()).supersedesId()).isNull();
            memories.erase(revision.id());
            assertHttp(HttpStatus.NOT_FOUND, () -> memories.get(revision.id()));
            assertThat(memories.listCurrent()).extracting(PersonalMemoryService.Memory::id)
                .doesNotContain(revision.id());

            authenticate(970002, "personal_os_ci_b");
            assertThat(memories.listPrivate()).extracting(PersonalMemoryService.Memory::id)
                .doesNotContain(restricted.id());
            assertHttp(HttpStatus.NOT_FOUND, () -> goals.get(goal.id()));
            assertHttp(HttpStatus.NOT_FOUND, () -> memories.get(restricted.id()));
            assertHttp(HttpStatus.NOT_FOUND, () -> memories.erase(restricted.id()));
            assertHttp(HttpStatus.NOT_FOUND, () -> memories.propose(
                new PersonalMemoryService.Proposed(
                    PERSON, "970002", HAS_EVENT_RECORD, RECORD, Long.toString(ownedRecord),
                    null, com.matrix.prp.ontology.PersonalOntologyAssertionGuard.EvidenceSource.RECORD,
                    Long.toString(ownedRecord), null, null, NORMAL, "pos_foreign_source_001")));
            System.out.println("CI_PERSONAL_OS_GOALS_MEMORY_REAL_MYSQL_LIFECYCLE=PASS");
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    private static void authenticate(long id, String username) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(
                new UserProfile(id, username, "Synthetic user"), null, List.of()));
    }

    private static void assertHttp(HttpStatus expected, org.assertj.core.api.ThrowableAssert.ThrowingCallable action) {
        assertThatThrownBy(action)
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(err -> assertThat(((ResponseStatusException)err).getStatusCode())
                .isEqualTo(expected));
    }
}
