package com.matrix.prp.records.api;

import com.matrix.prp.common.api.ApiResponse;
import com.matrix.prp.records.model.CreateRecordRequest;
import com.matrix.prp.records.model.RecordFilter;
import com.matrix.prp.records.model.RecordItem;
import com.matrix.prp.records.service.RecordService;
import jakarta.validation.Valid;
import java.time.LocalDate;
import java.util.List;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/records")
public class RecordController {

    private final RecordService recordService;

    public RecordController(RecordService recordService) {
        this.recordService = recordService;
    }

    @GetMapping
    public ApiResponse<List<RecordItem>> list(
            @RequestParam(required = false) String moduleCode,
            @RequestParam(required = false) Long tagId,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate recordDate,
            @RequestParam(required = false) String keyword) {
        return ApiResponse.success(recordService.list(new RecordFilter(moduleCode, tagId, recordDate, keyword)));
    }

    @PostMapping
    public ApiResponse<RecordItem> create(@Valid @RequestBody CreateRecordRequest request) {
        return ApiResponse.success(recordService.create(request));
    }

    @PutMapping("/{id}")
    public ApiResponse<RecordItem> update(@PathVariable long id, @Valid @RequestBody CreateRecordRequest request) {
        return ApiResponse.success(recordService.update(id, request));
    }

    @DeleteMapping("/{id}")
    public ApiResponse<Void> delete(@PathVariable long id) {
        recordService.delete(id);
        return ApiResponse.success();
    }
}
