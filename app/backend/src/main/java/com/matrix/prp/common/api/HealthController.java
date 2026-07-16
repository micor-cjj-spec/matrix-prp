package com.matrix.prp.common.api;

import java.time.OffsetDateTime;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/health")
public class HealthController {

    private static final String SERVICE_NAME = "matrix-prp-backend";
    private static final String VERSION = "0.1.0";
    private static final String API_CONTRACT = "phase-1-runtime-api";

    private final RuntimeHealthService runtimeHealthService;

    public HealthController(RuntimeHealthService runtimeHealthService) {
        this.runtimeHealthService = runtimeHealthService;
    }

    @GetMapping
    public ApiResponse<Map<String, Object>> health() {
        return ApiResponse.success(Map.of(
                "status", "UP",
                "service", SERVICE_NAME,
                "version", VERSION,
                "apiContract", API_CONTRACT,
                "time", OffsetDateTime.now().toString()));
    }

    @GetMapping("/runtime")
    public ApiResponse<RuntimeHealth> runtime() {
        return ApiResponse.success(runtimeHealthService.runtime());
    }
}
