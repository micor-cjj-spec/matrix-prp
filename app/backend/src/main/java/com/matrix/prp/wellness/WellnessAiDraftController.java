package com.matrix.prp.wellness;

import com.matrix.prp.common.api.ApiResponse;
import com.matrix.prp.ai.AiStore;
import com.matrix.prp.auth.security.CurrentUser;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

@RestController
@org.springframework.context.annotation.Profile("!test")
@RequestMapping("/api/wellness/ai")
public class WellnessAiDraftController {
    private final WellnessAiDraftService service;
    private final AiStore chat;
    public WellnessAiDraftController(WellnessAiDraftService service,AiStore chat){
        this.service=service; this.chat=chat;
    }

    public record ChatDraft(String conversationId,long messageId,WellnessAiDraftService.Preview draft) {}

    /**
     * Same verified nutrition draft as manual capture, but surfaced as a persisted inline chat card.
     * Never writes a meal or imports food until a separate owner-confirmed request.
     */
    @PostMapping(value="/chat/prepare",consumes=MediaType.MULTIPART_FORM_DATA_VALUE)
    public ApiResponse<ChatDraft> chatPrepare(
        @RequestParam @NotBlank @Size(max=1500) String text,
        @RequestParam(required=false) MultipartFile image,
        @RequestParam(required=false) String conversationId) {
        long user=CurrentUser.id();
        if(conversationId!=null && !conversationId.isBlank() && !chat.owns(user,conversationId))
            throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Conversation not found");
        WellnessAiDraftService.Preview draft=service.prepare(text,image);
        String id=conversationId==null||conversationId.isBlank()
            ? chat.create(user,text.substring(0,Math.min(48,text.length()))).id():conversationId;
        chat.append(user,id,"user",text);
        long assistant=chat.append(user,id,"assistant","已整理健康记录，请核对下方食物与来源，然后确认保存。");
        chat.saveBlocks(user,id,assistant,List.of(
            new AiStore.MessageBlock(assistant,"wellness_draft","wellness","待确认健康记录",draft.draftId())));
        return ApiResponse.success(new ChatDraft(id,assistant,draft));
    }

    @GetMapping("/drafts/{draftId}")
    public ApiResponse<WellnessAiDraftService.DraftView> getDraft(@PathVariable String draftId) {
        return ApiResponse.success(service.getDraft(draftId));
    }

    @PostMapping(value="/prepare",consumes=MediaType.MULTIPART_FORM_DATA_VALUE)
    public ApiResponse<WellnessAiDraftService.Preview> prepare(
        @RequestParam @NotBlank @Size(max=1500) String text,
        @RequestParam(required=false) MultipartFile image){
        return ApiResponse.success(service.prepare(text,image));
    }
    @PatchMapping("/drafts/{draftId}")
    public ApiResponse<WellnessAiDraftService.Preview> edit(@PathVariable String draftId,
        @RequestBody com.fasterxml.jackson.databind.JsonNode changes) {
        return ApiResponse.success(service.edit(draftId,changes));
    }
    @PostMapping("/drafts/{draftId}/confirm")
    public ApiResponse<WellnessAiDraftService.Outcome> confirm(@PathVariable String draftId){
        return ApiResponse.success(service.confirm(draftId));
    }
}
