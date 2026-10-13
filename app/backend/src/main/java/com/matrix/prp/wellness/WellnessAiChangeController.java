package com.matrix.prp.wellness;
import com.fasterxml.jackson.databind.JsonNode;
import com.matrix.prp.common.api.ApiResponse;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.*;

@RestController
@Profile("!test")
@RequestMapping("/api/wellness/ai/changes")
public class WellnessAiChangeController {
    private final WellnessAiChangeService service;
    public WellnessAiChangeController(WellnessAiChangeService service){this.service=service;}
    @PostMapping("/prepare")
    public ApiResponse<WellnessAiChangeService.Preview> prepare(
        @RequestBody WellnessAiChangeService.Request request) {
        return ApiResponse.success(service.prepare(request));
    }
    @PatchMapping("/{id}")
    public ApiResponse<WellnessAiChangeService.Preview> edit(@PathVariable String id,
        @RequestBody JsonNode after) {
        return ApiResponse.success(service.edit(id,after));
    }
    @PostMapping("/{id}/confirm")
    public ApiResponse<WellnessAiChangeService.Result> confirm(@PathVariable String id) {
        return ApiResponse.success(service.confirm(id));
    }
}
