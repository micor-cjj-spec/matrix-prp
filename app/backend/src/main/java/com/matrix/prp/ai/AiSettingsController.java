package com.matrix.prp.ai;

import com.matrix.prp.common.api.ApiResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/ai/settings")
public class AiSettingsController {
    public record CredentialRequest(@NotBlank @Size(max=1024) String apiKey) {}
    public record SelectionRequest(@NotBlank String provider, @NotBlank String model) {}
    private final AiSettingsService service;
    public AiSettingsController(AiSettingsService service) { this.service = service; }

    @GetMapping
    public ResponseEntity<ApiResponse<AiSettingsService.Settings>> read() {
        return secretSafe(service.settings());
    }
    @PutMapping("/providers/{provider}/key")
    public ResponseEntity<ApiResponse<AiSettingsService.Settings>> saveKey(
            @PathVariable String provider, @Valid @RequestBody CredentialRequest request) {
        return secretSafe(service.saveKey(provider, request.apiKey()));
    }
    @DeleteMapping("/providers/{provider}/key")
    public ResponseEntity<ApiResponse<AiSettingsService.Settings>> deleteKey(@PathVariable String provider) {
        return secretSafe(service.removeKey(provider));
    }
    @PutMapping("/selection")
    public ResponseEntity<ApiResponse<AiSettingsService.Settings>> select(@Valid @RequestBody SelectionRequest request) {
        return secretSafe(service.choose(request.provider(), request.model()));
    }
    @PostMapping("/providers/{provider}/test")
    public ResponseEntity<ApiResponse<Map<String, Object>>> test(@PathVariable String provider,
            @Valid @RequestBody SelectionRequest request) {
        if (!provider.equals(request.provider()))
            throw new org.springframework.web.server.ResponseStatusException(
                org.springframework.http.HttpStatus.BAD_REQUEST, "Provider mismatch");
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(ApiResponse.success(
            service.test(provider, request.model())));
    }
    private static ResponseEntity<ApiResponse<AiSettingsService.Settings>> secretSafe(AiSettingsService.Settings value) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(ApiResponse.success(value));
    }
}
