package com.matrix.prp.ai;

import com.matrix.prp.common.api.ApiResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;
import java.util.List;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/** Preview grants no persistent permission; chat must carry a separate explicit one-shot consent. */
@RestController
@RequestMapping("/api/ai/context")
public class AiContextController {
    public record PreviewRequest(@NotEmpty @Size(max = 3) List<String> scopes) {}
    private final AiContextService context;
    public AiContextController(AiContextService context) { this.context = context; }

    @PostMapping("/preview")
    public ResponseEntity<ApiResponse<AiContextService.Snapshot>> preview(
            @Valid @RequestBody PreviewRequest request) {
        AiContextService.Snapshot snapshot = context.preview(request.scopes());
        context.json(snapshot); // enforce same size bound as actual provider request
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(ApiResponse.success(snapshot));
    }
}
