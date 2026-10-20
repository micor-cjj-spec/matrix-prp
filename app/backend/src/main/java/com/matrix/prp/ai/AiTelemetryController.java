package com.matrix.prp.ai;

import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.common.api.ApiResponse;
import java.util.Set;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/ai/telemetry")
public class AiTelemetryController {
    private final AiInvocationAudit audit;
    public AiTelemetryController(AiInvocationAudit audit) { this.audit = audit; }

    @GetMapping
    public ResponseEntity<ApiResponse<AiInvocationAudit.Report>> mine(
            @RequestParam(defaultValue="7") int days,
            @RequestParam(defaultValue="20") int limit) {
        if (!Set.of(1,7,30).contains(days))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"days must be 1, 7 or 30");
        if (limit<1 || limit>50)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"limit must be 1-50");
        long user = CurrentUser.id();
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(ApiResponse.success(new AiInvocationAudit.Report(
                audit.summary(user,days),audit.recent(user,days,limit),
                "UNAVAILABLE_NO_VERIFIED_MODEL_PRICING")));
    }
}
