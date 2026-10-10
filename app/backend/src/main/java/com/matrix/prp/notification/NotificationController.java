package com.matrix.prp.notification;

import com.matrix.prp.common.api.ApiResponse;
import com.matrix.prp.notification.NotificationService.RuleRequest;
import com.matrix.prp.notification.NotificationService.SubscriptionRequest;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.*;

@RestController
@Profile("!test")
public class NotificationController {
    private final NotificationService service;
    private final String publicKey;
    public NotificationController(NotificationService service,@Value("${MATRIX_PRP_VAPID_PUBLIC_KEY:}") String publicKey){
        this.service=service;this.publicKey=publicKey;
    }
    @GetMapping("/api/notification-rules")
    public ApiResponse<List<Map<String,Object>>> rules(){return ApiResponse.success(service.rules());}
    @PostMapping("/api/notification-rules")
    public ApiResponse<Long> create(@RequestBody RuleRequest r){return ApiResponse.success(service.create(r));}
    @PutMapping("/api/notification-rules/{id}")
    public ApiResponse<Void> update(@PathVariable long id,@RequestBody RuleRequest r){service.update(id,r);return ApiResponse.success();}
    @PatchMapping("/api/notification-rules/{id}/status")
    public ApiResponse<Void> status(@PathVariable long id,@RequestParam boolean enabled){service.status(id,enabled);return ApiResponse.success();}
    @DeleteMapping("/api/notification-rules/{id}")
    public ApiResponse<Void> delete(@PathVariable long id){service.delete(id);return ApiResponse.success();}
    @PostMapping("/api/notification-rules/send-now")
    public ApiResponse<Long> sendNow(@RequestBody RuleRequest r){return ApiResponse.success(service.sendNow(r));}
    @GetMapping("/api/notifications")
    public ApiResponse<List<Map<String,Object>>> inbox(){return ApiResponse.success(service.inbox());}
    @PatchMapping("/api/notifications/{id}/read")
    public ApiResponse<Void> read(@PathVariable long id){service.markRead(id);return ApiResponse.success();}
    @GetMapping("/api/push/vapid-public-key")
    public ApiResponse<String> publicKey(){return ApiResponse.success(publicKey);}
    @PostMapping("/api/push/subscriptions")
    public ApiResponse<String> subscribe(@RequestBody SubscriptionRequest r){return ApiResponse.success(service.subscribe(r));}
    public record EndpointRequest(String endpoint) {}
    @PostMapping("/api/push/subscriptions/unsubscribe-current")
    public ApiResponse<Void> unsubscribeCurrent(@RequestBody EndpointRequest request){
        service.unsubscribeCurrent(request.endpoint());
        return ApiResponse.success();
    }
    @GetMapping("/api/push/subscriptions")
    public ApiResponse<List<Map<String,Object>>> devices(){return ApiResponse.success(service.devices());}
    @DeleteMapping("/api/push/subscriptions/{id}")
    public ApiResponse<Void> unsubscribe(@PathVariable long id){service.unsubscribe(id);return ApiResponse.success();}
    @PostMapping("/api/push/test")
    public ApiResponse<Long> test(){return ApiResponse.success(service.sendTest());}
}


