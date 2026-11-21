package com.matrix.prp.memory;

import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.memory.PersonalMemoryService.AiCandidate;
import com.matrix.prp.memory.PersonalMemoryService.Memory;
import java.util.HashSet;
import java.util.List;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/**
 * T-008a: first-party intake of structured suggestions from an AI-assisted UI.
 * Saves PENDING candidates only. No model invocation, chat intercept or MCP.
 */
@Service
@Profile("!test")
public class PersonalAiCandidateIntakeService {
    private static final int MAX_BATCH = 5;
    private final PersonalMemoryService memories;

    public PersonalAiCandidateIntakeService(PersonalMemoryService memories) {
        this.memories = memories;
    }

    /** Inspect previously suggested facts without writing or exporting existing private values. */
    public List<PersonalMemoryService.AiInspection> inspect(List<AiCandidate> candidates) {
        validateBatch(candidates);
        return candidates.stream().map(memories::inspectAiCandidate).toList();
    }

    @Transactional
    public List<Memory> submit(List<AiCandidate> candidates) {
        validateBatch(candidates);
        return candidates.stream().map(memories::proposeAiCandidate).toList();
    }

    private void validateBatch(List<AiCandidate> candidates) {
        CurrentUser.id();
        if (candidates == null || candidates.isEmpty() || candidates.size() > MAX_BATCH)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                "AI knowledge candidate batch must contain 1 to 5 items");
        var keys = new HashSet<String>();
        // Validate all batch-local idempotency keys before any persistence.
        for (AiCandidate item : candidates) {
            if (item == null || item.requestKey() == null
                    || !item.requestKey().matches("[a-zA-Z0-9_-]{8,80}")
                    || !keys.add(item.requestKey())) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "Missing, invalid or duplicate AI candidate request key");
            }
        }
    }
}
