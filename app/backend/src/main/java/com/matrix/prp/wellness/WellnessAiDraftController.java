package com.matrix.prp.wellness;

import com.matrix.prp.common.api.ApiResponse;
import com.matrix.prp.ai.AiStore;
import com.matrix.prp.auth.security.CurrentUser;
import java.util.List;
import java.util.ArrayList;
import java.util.Set;
import org.springframework.transaction.annotation.Transactional;
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
        boolean hasImage=image!=null && !image.isEmpty();
        WellnessAiDraftService.Preview draft=hasImage?null:service.prepareBatch(text);
        if(draft==null && !hasImage) draft=service.prepareRepeat(text);
        if(draft==null && !hasImage && conversationId!=null && !conversationId.isBlank() &&
            text.matches("(?s).*晚餐也帮我(?:录入|录人|记录|保存).*")) {
            // User's brief follow-up can reuse the earlier *user supplied* full meal note.
            // Never ask the model to invent a meal missing from this message.
            List<AiStore.Message> history=chat.messages(user,conversationId,null,30);
            for(int i=history.size()-1;i>=0;i--) {
                var message=history.get(i);
                if(!"user".equals(message.role())) continue;
                try { draft=service.prepareBatch(message.content(),"DINNER"); }
                catch(ResponseStatusException ex) {
                    if(ex.getStatusCode().value()==409) throw ex;
                }
                if(draft!=null)break;
            }
            // If no multi-meal note exists, the general contextual draft path
            // below can still reuse a single meal without hallucinating detail.
        }
        if(draft==null && !hasImage && WellnessChatMealRequest.isContextualFollowup(text)) {
            if(conversationId==null || conversationId.isBlank())
                throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY,
                    "当前没有可引用的餐食对话，请先告诉我吃了什么，再生成健康记录卡片");
            // Resolve only messages owned by this authenticated conversation.
            // The model's previous calorie estimate is a suggestion, never a write receipt.
            draft=service.prepareConversationMeal(
                chat.messages(user,conversationId,null,80),text);
        }
        if(draft==null) draft=service.prepare(text,image);
        String id=conversationId==null||conversationId.isBlank()
            ? chat.create(user,text.substring(0,Math.min(48,text.length()))).id():conversationId;
        chat.append(user,id,"user",text);
        long assistant=chat.append(user,id,"assistant","已整理健康记录，请核对下方食物与来源，然后确认保存。");
        chat.saveBlocks(user,id,assistant,List.of(
            new AiStore.MessageBlock(assistant,"wellness_draft","wellness","待确认健康记录",draft.draftId())));
        return ApiResponse.success(new ChatDraft(id,assistant,draft));
    }

    public record ChatConfirmationRequest(String conversationId,String message) {}
    public record ChatConfirmation(long messageId,String content,String status,String route) {}

    /**
     * Strictly confirm one owner-bound preview from this conversation. A reply like
     * "确认保存" cannot be handed to a language model to hallucinate a write receipt.
     */
    @Transactional
    @PostMapping("/chat/confirm-pending")
    public ApiResponse<ChatConfirmation> confirmPending(@RequestBody ChatConfirmationRequest request) {
        long user=CurrentUser.id();
        if(request==null || request.conversationId()==null ||
            !chat.owns(user,request.conversationId()))
            throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Conversation not found");
        String words=request.message()==null?"":request.message().strip();
        if(!words.matches("^(?:是的|对|嗯|确认|确认保存|确认录入|保存|保存吧|保存一下|好的|可以|没错|是|帮我保存到健康中心)$"))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"请明确确认当前待保存餐次");
        List<AiStore.MessageBlock> blocks=chat.blocks(user,request.conversationId()).stream()
            .filter(b->"wellness_draft".equals(b.type()) &&
                b.route()!=null && b.route().matches("[0-9a-fA-F-]{36}")).toList();
        List<WellnessAiDraftService.DraftView> pending=new ArrayList<>();
        WellnessAiDraftService.DraftView mostRecent=null;
        for(var block:blocks) {
            WellnessAiDraftService.DraftView view=service.getDraft(block.route());
            if(mostRecent==null)mostRecent=view;
            if("PENDING".equals(view.status()) &&
                java.time.LocalDateTime.parse(view.draft().expiresAt())
                    .isAfter(java.time.LocalDateTime.now()))
                pending.add(view);
        }
        String response,route="",status;
        if(pending.size()>1) {
            response="当前会话有多个待确认饮食草稿，请点击对应卡片的「确认保存」，避免保存错日期或餐次。";
            status="MULTIPLE_PENDING";
        } else if(pending.size()==1) {
            var selected=pending.getFirst();
            var outcome=service.confirm(selected.draft().draftId());
            Object saved=outcome.saved();
            if(saved instanceof List<?> records) {
                StringBuilder summary=new StringBuilder();
                for(Object item:records) if(item instanceof WellnessModels.Meal meal) {
                    if(!summary.isEmpty())summary.append("、");
                    summary.append(meal.mealDate()).append(" ")
                        .append(switch(meal.mealType()){
                            case "BREAKFAST"->"早餐";case "LUNCH"->"午餐";
                            case "DINNER"->"晚餐";default->"加餐";
                        }).append("（记录ID ").append(meal.id()).append("）");
                }
                response="已由健康中心确认保存："+summary+"。";
            } else if(saved instanceof WellnessModels.Meal meal) {
                response="已由健康中心确认保存："+meal.mealDate()+" "+
                    meal.mealType()+"（记录ID "+meal.id()+"）。";
            } else response="健康中心已确认保存本条记录。";
            status="SAVED";
            route=outcome.route();
        } else if(mostRecent!=null && "CONSUMED".equals(mostRecent.status())) {
            response="这份饮食草稿已确认保存过，没有再次创建记录。请在健康中心核对。";
            status="ALREADY_SAVED";
            route="/wellness?date="+mostRecent.draft().values().get("date");
        } else {
            response="当前会话没有可确认的待保存饮食草稿；请先提供日期、餐次、食物与热量。";
            status="NO_PENDING";
        }
        chat.append(user,request.conversationId(),"user",words);
        long assistant=chat.append(user,request.conversationId(),"assistant",response);
        return ApiResponse.success(new ChatConfirmation(assistant,response,status,route));
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
