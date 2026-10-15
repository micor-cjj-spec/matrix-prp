package com.matrix.prp.finance.imports;

import com.matrix.prp.common.api.ApiResponse;
import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@Profile("!test")
@RequestMapping("/api/finance/imports")
public class FinanceImportController {
    private final FinanceImportService service;
    public FinanceImportController(FinanceImportService service) { this.service=service; }

    @PostMapping(value="/wechat/preview",consumes=MediaType.MULTIPART_FORM_DATA_VALUE)
    public ApiResponse<FinanceImportService.BatchView> preview(
            @RequestParam("file") MultipartFile file,
            @RequestParam(value="sourceAccountKey",required=false) String sourceAccountKey) {
        return ApiResponse.success(service.preview(file,sourceAccountKey));
    }
    @GetMapping
    public ApiResponse<List<FinanceImportService.HistoryItem>> history() {
        return ApiResponse.success(service.history());
    }
    @GetMapping("/{id}")
    public ApiResponse<FinanceImportService.BatchView> detail(@PathVariable long id) {
        return ApiResponse.success(service.detail(id));
    }
    @PostMapping("/{id}/commit")
    public ApiResponse<FinanceImportService.BatchView> commit(@PathVariable long id,
            @RequestBody FinanceImportService.CommitRequest request) {
        return ApiResponse.success(service.commit(id,request));
    }
}
