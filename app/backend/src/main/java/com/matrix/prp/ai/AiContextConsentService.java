package com.matrix.prp.ai;

import com.matrix.prp.auth.security.CurrentUser;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

/**
 * Single-node, short-lived one-shot data sharing permits.
 * A preview is NOT consent; only an explicit confirm action issues a send token.
 * Neither preview data nor confirmation tokens are persisted in chat history.
 */
@Service
public class AiContextConsentService {
    private static final long TTL_MILLIS = 3 * 60_000L;
    private static final int MAX_PENDING = 2048;
    public record Prepared(String previewId, List<String> scopes, LocalDate date, Map<String,Object> data) {}
    public record Confirmed(String contextToken, List<String> scopes) {}
    private record Grant(long userId, AiContextService.Snapshot snapshot,
                         String provider, String model, long expiresAt) {}

    private final AiContextService context;
    private final AiSettingsService settings;
    private final ConcurrentHashMap<String, Grant> previews = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, Grant> confirmed = new ConcurrentHashMap<>();

    public AiContextConsentService(AiContextService context, AiSettingsService settings) {
        this.context = context; this.settings = settings;
    }

    public Prepared preview(List<String> scopes) {
        long user = CurrentUser.id();
        AiContextService.Snapshot snapshot = context.preview(scopes);
        context.json(snapshot); // fail closed on oversized context
        purgeExpired();
        if (previews.size() + confirmed.size() >= MAX_PENDING)
            throw new ResponseStatusException(HttpStatus.TOO_MANY_REQUESTS, "Too many pending context approvals");
        AiSettingsStore.Selection chosen = settings.selection(user);
        String id = UUID.randomUUID().toString();
        previews.put(id, new Grant(user, snapshot, chosen.provider(), chosen.model(), expiry()));
        return new Prepared(id, snapshot.scopes(), snapshot.date(), snapshot.data());
    }

    public Confirmed confirm(String previewId) {
        long user = CurrentUser.id();
        Grant draft = previews.get(previewId);
        requireGrant(draft, user);
        if (!previews.remove(previewId, draft))
            throw invalid();
        String token = UUID.randomUUID().toString();
        confirmed.put(token, draft);
        return new Confirmed(token, draft.snapshot().scopes());
    }

    public AiContextService.Snapshot consume(String token, List<String> expectedScopes) {
        long user = CurrentUser.id();
        Grant grant = confirmed.get(token);
        requireGrant(grant, user);
        if (!grant.snapshot().scopes().equals(expectedScopes))
            throw invalid();
        if (!confirmed.remove(token, grant))
            throw invalid();
        return grant.snapshot();
    }

    private void requireGrant(Grant grant, long user) {
        if (grant == null || grant.userId() != user || System.currentTimeMillis() >= grant.expiresAt())
            throw invalid();
        AiSettingsStore.Selection chosen = settings.selection(user);
        if (!grant.provider().equals(chosen.provider()) || !grant.model().equals(chosen.model()))
            throw invalid();
    }
    public String augment(String userText, AiContextService.Snapshot snapshot) {
        return context.augmentPrompt(userText, snapshot);
    }

    private static long expiry() { return System.currentTimeMillis() + TTL_MILLIS; }
    private static ResponseStatusException invalid() {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, "Context approval missing, expired, or already used");
    }
    private void purgeExpired() {
        long now = System.currentTimeMillis();
        previews.entrySet().removeIf(item -> item.getValue().expiresAt() <= now);
        confirmed.entrySet().removeIf(item -> item.getValue().expiresAt() <= now);
    }
}
