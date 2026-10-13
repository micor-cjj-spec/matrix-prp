package com.matrix.prp.ai;

import com.matrix.prp.common.api.ApiResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;
import java.util.List;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/** Data access is explicit: preview -> confirm -> single use stream token. */
@RestController
@RequestMapping("/api/ai/context")
public class AiContextController {
    public record PreviewRequest(@NotEmpty @Size(max = 4) List<String> scopes) {}
    public record ConfirmRequest(@NotEmpty String previewId) {}
    private final AiContextConsentService consents;
    public AiContextController(AiContextConsentService consents) { this.consents = consents; }

    @PostMapping("/preview")
    public ResponseEntity<ApiResponse<AiContextConsentService.Prepared>> preview(
            @Valid @RequestBody PreviewRequest request) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(ApiResponse.success(consents.preview(request.scopes())));
    }
    @PostMapping("/confirm")
    public ResponseEntity<ApiResponse<AiContextConsentService.Confirmed>> confirm(
            @Valid @RequestBody ConfirmRequest request) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(ApiResponse.success(consents.confirm(request.previewId())));
    }
}
