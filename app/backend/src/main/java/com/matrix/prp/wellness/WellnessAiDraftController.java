package com.matrix.prp.wellness;

import com.matrix.prp.common.api.ApiResponse;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/wellness/ai")
public class WellnessAiDraftController {
    private final WellnessAiDraftService service;
    public WellnessAiDraftController(WellnessAiDraftService service){this.service=service;}

    @PostMapping(value="/prepare",consumes=MediaType.MULTIPART_FORM_DATA_VALUE)
    public ApiResponse<WellnessAiDraftService.Preview> prepare(
        @RequestParam @NotBlank @Size(max=1500) String text,
        @RequestParam(required=false) MultipartFile image){
        return ApiResponse.success(service.prepare(text,image));
    }
    @PostMapping("/drafts/{draftId}/confirm")
    public ApiResponse<WellnessAiDraftService.Outcome> confirm(@PathVariable String draftId){
        return ApiResponse.success(service.confirm(draftId));
    }
}
