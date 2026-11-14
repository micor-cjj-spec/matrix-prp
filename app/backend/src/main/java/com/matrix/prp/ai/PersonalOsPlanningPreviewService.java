package com.matrix.prp.ai;

import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.goals.GoalService;
import com.matrix.prp.memory.PersonalMemoryService;
import com.matrix.prp.ontology.PersonalOntology.NodeType;
import com.matrix.prp.ontology.PersonalOntology.Relation;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

/**
 * T-005: first-party, read-only evidence preview. This is NOT permission to
 * transmit personal data to a model, an MCP tool, or a task write endpoint.
 * Existing owner/evidence guards remain the source of truth.
 */
@Service
@Profile("!test")
public final class PersonalOsPlanningPreviewService {
    private static final int MAX_LINKS = 16;
    private static final int MAX_MEMORIES = 8;
    private static final int MAX_TEXT = 256;
    private static final Set<Relation> PERSONAL_PREDICATES =
        Set.of(Relation.DECLARES_SKILL, Relation.PREFERS, Relation.HAS_BACKGROUND);

    public record Evidence(String reference, String relation, String statement,
                           String evidenceClass) {}
    public record Gap(String code, String explanation) {}
    public record TaskDraft(String title, String rationale, List<String> evidenceRefs) {}
    public record Preview(long goalId, String title, String status, String successCriteria,
                          List<Evidence> evidence, List<Gap> gaps, List<TaskDraft> taskDrafts,
                          boolean modelInvoked, boolean dataWritten, String limitation) {}

    private final GoalService goals;
    private final PersonalMemoryService memories;

    public PersonalOsPlanningPreviewService(GoalService goals, PersonalMemoryService memories) {
        this.goals = goals;
        this.memories = memories;
    }

    /**
     * No arbitrary userId, free-text query or model-provided tool arguments.
     * Personal statements are read only after the caller explicitly opts in.
     */
    public Preview preview(long goalId, boolean includePersonalFacts) {
        long owner = CurrentUser.id();
        GoalService.Goal goal = goals.get(goalId); // owner-scoped, 404 for foreign/deleted
        if (!"career".equals(goal.domain())) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                "T-005 preview is limited to career goals");
        }
        List<Evidence> evidence = new ArrayList<>();
        evidence.add(new Evidence("goal:" + goal.id(), "GOAL", shortText(goal.title()), "USER_GOAL"));
        boolean hasSkillRequirement = false;
        boolean hasLinkedAction = false;

        // GoalService.context checks owner, relation types, validity, NORMAL-only
        // sensitivity, evidence ownership and a bounded result size.
        List<GoalService.Link> links = goals.context(goalId);
        for (GoalService.Link link : links) {
            if (evidence.size() >= MAX_LINKS + 1) break;
            String ref = "assertion:" + link.assertionId();
            if (link.assertionId() <= 0) continue;
            switch (link.predicate()) {
                case "NEEDS_SKILL" -> {
                    if (!"GOAL".equals(link.subjectType()) || !"LITERAL".equals(link.objectType())
                            || !Long.toString(goalId).equals(link.subjectRef())
                            || !validText(link.objectValue())) continue;
                    evidence.add(new Evidence(ref, "NEEDS_SKILL",
                        shortText(link.objectValue()), "USER_CONFIRMED_ASSERTION"));
                    hasSkillRequirement = true;
                }
                case "ADVANCES" -> {
                    if (!"TASK".equals(link.subjectType()) || !"GOAL".equals(link.objectType())
                            || !Long.toString(goalId).equals(link.objectRef())
                            || !validRef(link.subjectRef())) continue;
                    evidence.add(new Evidence(ref, "ADVANCES",
                        "TASK #" + link.subjectRef(), "OWNER_VERIFIED_REFERENCE"));
                    hasLinkedAction = true;
                }
                case "USES_RESOURCE_RECORD" -> {
                    if (!"GOAL".equals(link.subjectType()) || !"RECORD".equals(link.objectType())
                            || !Long.toString(goalId).equals(link.subjectRef())
                            || !validRef(link.objectRef())) continue;
                    evidence.add(new Evidence(ref, "USES_RESOURCE_RECORD",
                        "RECORD #" + link.objectRef(), "OWNER_VERIFIED_REFERENCE"));
                }
                case "EVALUATES" -> {
                    if (!"REVIEW".equals(link.subjectType()) || !"GOAL".equals(link.objectType())
                            || !Long.toString(goalId).equals(link.objectRef())
                            || !validRef(link.subjectRef())) continue;
                    evidence.add(new Evidence(ref, "EVALUATES",
                        "REVIEW #" + link.subjectRef(), "OWNER_VERIFIED_REFERENCE"));
                }
                default -> { /* Do not traverse arbitrary graph edges or dereference records. */ }
            }
        }

        if (includePersonalFacts) {
            int count = 0;
            // Do NOT call listPrivate or pending, even when includePersonalFacts=true.
            // listCurrent itself performs owner, CONFIRMED, NORMAL, date and source checks.
            for (PersonalMemoryService.Memory memory : memories.listCurrent()) {
                if (count >= MAX_MEMORIES) break;
                if (memory.id() <= 0
                        || memory.subjectType() != NodeType.PERSON
                        || !Long.toString(owner).equals(memory.subjectRef())
                        || !PERSONAL_PREDICATES.contains(memory.predicate())
                        || !"CONFIRMED".equals(memory.status())
                        || !"NORMAL".equals(memory.sensitivity())
                        || !validText(memory.objectValue())
                        || memory.objectType() != NodeType.LITERAL
                        || memory.objectRef() != null
                        || (memory.validFrom() != null && memory.validFrom().isAfter(LocalDate.now()))
                        || (memory.validTo() != null && memory.validTo().isBefore(LocalDate.now()))) {
                    continue;
                }
                evidence.add(new Evidence("assertion:" + memory.id(),
                    memory.predicate().name(), shortText(memory.objectValue()),
                    "USER_CONFIRMED_SELF_REPORT"));
                count++;
            }
        }

        List<Gap> gaps = new ArrayList<>();
        List<TaskDraft> drafts = new ArrayList<>();
        String goalRef = "goal:" + goal.id();
        if (goal.successCriteria() == null || goal.successCriteria().isBlank()) {
            gaps.add(new Gap("SUCCESS_CRITERIA_UNSPECIFIED",
                "尚无可核验的成功标准；未填写不代表目标失败。"));
        }
        if (!hasSkillRequirement) {
            gaps.add(new Gap("SKILL_REQUIREMENTS_UNRECORDED",
                "本次有界查询中未检索到已确认的技能要求，不代表确实不需要技能。"));
        }
        if (!hasLinkedAction) {
            gaps.add(new Gap("TASK_RELATION_UNRECORDED",
                "本次有界查询中未检索到关联任务，不代表任务列表为空。"));
        }
        if (!includePersonalFacts) {
            gaps.add(new Gap("PERSONAL_FACTS_NOT_SELECTED",
                "本次未选择个人事实；不根据缺失的信息推断技能水平或偏好。"));
        }
        boolean active = Set.of("PLANNED", "ACTIVE", "PAUSED").contains(goal.status());
        if (active) {
            if (goal.successCriteria() == null || goal.successCriteria().isBlank()) {
                drafts.add(new TaskDraft("核对并确认目标成功标准",
                    "先明确如何检验目标是否达成。", List.of(goalRef)));
            }
            if (!hasSkillRequirement) {
                drafts.add(new TaskDraft("确认职业目标所需的关键技能",
                    "识别信息缺口，而非断定用户缺少技能。", List.of(goalRef)));
            }
            if (!hasLinkedAction) {
                drafts.add(new TaskDraft("草拟第一项可执行任务",
                    "候选草稿，不创建或修改任务。", List.of(goalRef)));
            }
        }
        return new Preview(goal.id(), shortText(goal.title()), goal.status(),
            shortText(goal.successCriteria()), List.copyOf(evidence), List.copyOf(gaps),
            List.copyOf(drafts), false, false,
            "仅供本人审阅的有界证据与规则草稿；未调用模型、未向外发送数据、未写任务。"
            + " 未返回的数据一律视为未知，不等于零。");
    }

    private static boolean validRef(String value) {
        return value != null && value.matches("[1-9][0-9]{0,18}");
    }
    private static boolean validText(String value) {
        return value != null && !value.isBlank() && value.length() <= MAX_TEXT;
    }
    private static String shortText(String value) {
        if (value == null) return null;
        return value.length() <= MAX_TEXT ? value : value.substring(0, MAX_TEXT);
    }
}
