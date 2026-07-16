package com.matrix.prp.modules.api;

import com.matrix.prp.common.api.ApiResponse;
import com.matrix.prp.modules.model.ModuleItem;
import com.matrix.prp.modules.service.ModuleService;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/modules")
public class ModuleController {

    private final ModuleService moduleService;

    public ModuleController(ModuleService moduleService) {
        this.moduleService = moduleService;
    }

    @GetMapping
    public ApiResponse<List<ModuleItem>> list() {
        return ApiResponse.success(moduleService.list());
    }

    @GetMapping("/features")
    public ApiResponse<List<ModuleItem>> listFeatures() {
        return ApiResponse.success(moduleService.listFeatures());
    }

    @GetMapping("/domains")
    public ApiResponse<List<ModuleItem>> listDomains() {
        return ApiResponse.success(moduleService.listDomains());
    }
}
