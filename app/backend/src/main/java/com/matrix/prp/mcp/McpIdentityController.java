package com.matrix.prp.mcp;

import com.matrix.prp.common.api.ApiResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.List;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/** First-party PRP JWT: user creates the ticket and may revoke their mapping. */
@RestController
@RequestMapping("/api/mcp/identity")
@ConditionalOnProperty(prefix = "matrix-prp.mcp.oauth", name = "enabled", havingValue = "true")
public class McpIdentityController {
    public record TicketRequest(@NotBlank String clientId, @NotBlank String password) {}
    public record UnlinkRequest(@NotBlank String password) {}
    private final McpIdentityLinkService service;

    public McpIdentityController(McpIdentityLinkService service) { this.service = service; }

    @GetMapping
    public ResponseEntity<ApiResponse<List<McpIdentityLinkService.Link>>> mine() {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(ApiResponse.success(service.myLinks()));
    }

    @PostMapping("/tickets")
    public ResponseEntity<ApiResponse<McpIdentityLinkService.Ticket>> ticket(
            @Valid @RequestBody TicketRequest input) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(ApiResponse.success(service.issueTicket(input.clientId(), input.password())));
    }

    @PostMapping("/unlink")
    public ResponseEntity<ApiResponse<Void>> unlink(@Valid @RequestBody UnlinkRequest input) {
        service.unlink(input.password());
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(ApiResponse.success());
    }
}
