package com.matrix.prp.ai;

import com.matrix.prp.common.api.ApiResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import org.springframework.context.annotation.Profile;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/** First-party only. Deliberately no MCP tool registration or write operation. */
@RestController
@Profile("!test")
@RequestMapping("/api/ai/personal-os/extract")
public final class PersonalOsChatExtractionController {
    public record PreviewRequest(@NotBlank String conversationId, @NotNull @Positive Long messageId) {}
    public record ConfirmRequest(@NotBlank String previewId) {}
    public record ExtractRequest(@NotBlank String extractionToken) {}

    private final PersonalOsChatExtractionService service;
    public PersonalOsChatExtractionController(PersonalOsChatExtractionService service) {
        this.service=service;
    }

    @PostMapping("/preview")
    public ResponseEntity<ApiResponse<PersonalOsChatExtractionService.Preview>> preview(
            @Valid @RequestBody PreviewRequest req) {
        return ok(service.preview(req.conversationId(),req.messageId()));
    }
    @PostMapping("/confirm")
    public ResponseEntity<ApiResponse<PersonalOsChatExtractionService.Approved>> confirm(
            @Valid @RequestBody ConfirmRequest req) {
        return ok(service.confirm(req.previewId()));
    }
    @PostMapping("/extract")
    public ResponseEntity<ApiResponse<PersonalOsChatExtractionService.Extraction>> extract(
            @Valid @RequestBody ExtractRequest req) {
        return ok(service.extract(req.extractionToken()));
    }

    private static <T> ResponseEntity<ApiResponse<T>> ok(T value) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(ApiResponse.success(value));
    }
}
