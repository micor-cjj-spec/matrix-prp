package com.matrix.prp.goals;

import com.matrix.prp.common.api.ApiResponse;
import java.util.List;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.*;

/** First-party authenticated goal endpoints; never published as MCP tools by default. */
@RestController
@Profile("!test")
@RequestMapping("/api/goals")
public final class GoalController {
    private final GoalService service;
    public GoalController(GoalService service) { this.service = service; }

    @GetMapping
    public ApiResponse<List<GoalService.Goal>> list() {
        return ApiResponse.success(service.list());
    }
    @GetMapping("/{id}")
    public ApiResponse<GoalService.Goal> get(@PathVariable long id) {
        return ApiResponse.success(service.get(id));
    }
    @PostMapping
    public ApiResponse<GoalService.Goal> create(@RequestBody GoalService.Create request) {
        return ApiResponse.success(service.create(request));
    }
    @PatchMapping("/{id}/status")
    public ApiResponse<GoalService.Goal> status(@PathVariable long id, @RequestParam String status) {
        return ApiResponse.success(service.changeStatus(id, status));
    }
    @GetMapping("/{id}/context")
    public ApiResponse<List<GoalService.Link>> context(@PathVariable long id) {
        return ApiResponse.success(service.context(id));
    }
    @DeleteMapping("/{id}")
    public ApiResponse<Void> delete(@PathVariable long id) {
        service.delete(id);
        return ApiResponse.success();
    }
}
