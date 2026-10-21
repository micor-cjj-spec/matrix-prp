package com.matrix.prp.vocal;

import com.matrix.prp.ai.AiProviderClient;
import com.matrix.prp.ai.AiSettingsService;
import com.matrix.prp.ai.AiStore;
import com.matrix.prp.ai.DeepSeekClient;
import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.common.api.ApiResponse;
import java.io.IOException;
import java.nio.file.Files;
import java.time.YearMonth;
import java.time.ZoneOffset;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@RestController
@Profile("!test")
@RequestMapping("/api/vocal")
public class VocalController {
    private final VocalService service;
    private final AiSettingsService settings;
    private final AiProviderClient provider;
    private final AiStore usage;
    private final int userRequests,globalRequests;
    private final long userTokens,globalTokens;
    public VocalController(VocalService service,AiSettingsService settings,AiProviderClient provider,AiStore usage,
        @Value("${matrix-prp.ai.user-monthly-requests:2000}") int ur,
        @Value("${matrix-prp.ai.global-monthly-requests:10000}") int gr,
        @Value("${matrix-prp.ai.user-monthly-reserved-tokens:12000000}") long ut,
        @Value("${matrix-prp.ai.global-monthly-reserved-tokens:60000000}") long gt) {
        this.service=service;this.settings=settings;this.provider=provider;this.usage=usage;
        this.userRequests=ur;this.globalRequests=gr;this.userTokens=ut;this.globalTokens=gt;
    }
    @GetMapping("/exercises")
    public ApiResponse<?> exercises(){return ApiResponse.success(service.exercises());}
    @GetMapping("/takes")
    public ApiResponse<List<VocalService.Take>> takes(){return ApiResponse.success(service.list());}
    @PostMapping(value="/takes",consumes=MediaType.MULTIPART_FORM_DATA_VALUE)
    public ApiResponse<VocalService.Take> upload(@RequestParam MultipartFile file,
        @RequestParam String exerciseCode,@RequestParam(required=false) String note,
        @RequestParam int durationSeconds,@RequestParam String samples,
        @RequestParam(required=false) Long songId,@RequestParam(required=false) Long sectionId) throws IOException {
        return ApiResponse.success(service.upload(exerciseCode,note,durationSeconds,samples,file,songId,sectionId));
    }
    @GetMapping("/takes/{id}/audio")
    public ResponseEntity<FileSystemResource> audio(@PathVariable long id) throws IOException {
        VocalService.Audio media=service.audio(id);
        return ResponseEntity.ok()
          .header(HttpHeaders.CACHE_CONTROL,"private, no-store")
          .header("X-Content-Type-Options","nosniff")
          .header(HttpHeaders.CONTENT_DISPOSITION,"attachment; filename=recording")
          .contentType(MediaType.parseMediaType(media.mimeType()))
          .contentLength(media.size()).body(new FileSystemResource(media.file()));
    }
    @DeleteMapping("/takes/{id}")
    public ApiResponse<Void> delete(@PathVariable long id){service.delete(id);return ApiResponse.success();}
    @PostMapping("/takes/{id}/coach")
    public ApiResponse<VocalService.Take> coach(@PathVariable long id) {
        VocalService.Take take=service.get(id);
        if("DONE".equals(take.aiStatus())) return ApiResponse.success(take);
        // Lock a single take to avoid accidental duplicate billing from repeated UI clicks.
        if(!service.claimAnalysis(id))
            throw new ResponseStatusException(HttpStatus.CONFLICT,"AI analysis in progress; refresh later");
        try {
            long user=CurrentUser.id();
            var runtime=settings.resolve(user);
            String month=YearMonth.now(ZoneOffset.UTC).toString();
            usage.reserve(user,month,2048,userRequests,userTokens,globalRequests,globalTokens);
            String prompt="你是谨慎、友善、务实的中文声乐练习指导助手。"
                +"以下数据仅为手机端估算的音高指标，不是直接听音结果，不可声称听过录音。"
                +"不要诊断声带或判断气息、共鸣、喉部疾病；若用户疼痛或持续嘶哑建议停止并咨询专业人员。"
                +"用120字以内给出一条观察、两条具体的下次练习建议。"
                +"练习："+take.exerciseCode()+"；时长："+take.durationSeconds()+"秒；备注："+take.note()
                +"；分析："+take.analysis();
            var answer=provider.stream(runtime,List.of(
                new DeepSeekClient.ChatMessage("user",prompt)),350,s->{});
            usage.completed(user,month,answer.inputTokens(),answer.outputTokens());
            String feedback=answer.answer().length()>1500?answer.answer().substring(0,1500):answer.answer();
            service.finishAnalysis(id,feedback,true);
            return ApiResponse.success(service.get(id));
        } catch (ResponseStatusException ex) {
            service.finishAnalysis(id,null,false);throw ex;
        } catch (Exception ex) {
            service.finishAnalysis(id,null,false);
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,"AI 教练暂不可用，请稍后重试");
        }
    }
}
