package com.matrix.prp.activity;
import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.common.api.ApiResponse;
import java.util.List;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
@RestController
@RequestMapping("/api/activity")
public class ActivityLogController {
    private final ActivityLogStore logs;
    public ActivityLogController(ActivityLogStore logs) { this.logs=logs; }
    @GetMapping("/mine")
    public ResponseEntity<ApiResponse<List<ActivityLogStore.Entry>>> mine(
        @RequestParam(defaultValue="7") int days,@RequestParam(defaultValue="20") int limit) {
        if(days!=1 && days!=7 && days!=30)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"days must be 1, 7 or 30");
        if(limit<1 || limit>50)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"limit must be 1-50");
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(ApiResponse.success(logs.recent(CurrentUser.id(),days,limit)));
    }
}
