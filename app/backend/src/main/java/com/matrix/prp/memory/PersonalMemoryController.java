package com.matrix.prp.memory;

import com.matrix.prp.common.api.ApiResponse;
import java.util.List;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.*;

/**
 * Authenticated first-party memory review. No automatically approved AI writes.
 * Never register these endpoints as general MCP write tools.
 */
@RestController
@Profile("!test")
@RequestMapping("/api/memory")
public final class PersonalMemoryController {
    private final PersonalMemoryService service;
    public PersonalMemoryController(PersonalMemoryService service) { this.service=service; }

    @GetMapping public ApiResponse<List<PersonalMemoryService.Memory>> list() {
        return ApiResponse.success(service.listCurrent());
    }
    @GetMapping("/candidates") public ApiResponse<List<PersonalMemoryService.Memory>> pending() {
        return ApiResponse.success(service.pending());
    }
    @GetMapping("/{id}") public ApiResponse<PersonalMemoryService.Memory> get(@PathVariable long id) {
        return ApiResponse.success(service.get(id));
    }
    @PostMapping("/candidates")
    public ApiResponse<PersonalMemoryService.Memory> propose(
        @RequestBody PersonalMemoryService.Proposed input) {
        return ApiResponse.success(service.propose(input));
    }
    @PostMapping("/{id}/replacement")
    public ApiResponse<PersonalMemoryService.Memory> replace(
        @PathVariable long id, @RequestBody PersonalMemoryService.Proposed input) {
        return ApiResponse.success(service.proposeReplacement(id,input));
    }
    @PostMapping("/{id}/confirm")
    public ApiResponse<PersonalMemoryService.Memory> confirm(@PathVariable long id) {
        return ApiResponse.success(service.confirm(id));
    }
    @PostMapping("/{id}/invalidate")
    public ApiResponse<PersonalMemoryService.Memory> invalidate(@PathVariable long id) {
        return ApiResponse.success(service.invalidate(id));
    }
    @DeleteMapping("/{id}")
    public ApiResponse<Void> erase(@PathVariable long id) {
        service.erase(id);
        return ApiResponse.success();
    }
}
