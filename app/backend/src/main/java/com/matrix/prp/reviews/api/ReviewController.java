package com.matrix.prp.reviews.api;

import com.matrix.prp.common.api.ApiResponse;
import com.matrix.prp.reviews.model.CreateReviewRequest;
import com.matrix.prp.reviews.model.ReviewFilter;
import com.matrix.prp.reviews.model.ReviewItem;
import com.matrix.prp.reviews.service.ReviewService;
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
@RequestMapping("/api/reviews")
public class ReviewController {

    private final ReviewService reviewService;

    public ReviewController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @GetMapping
    public ApiResponse<List<ReviewItem>> list(
            @RequestParam(required = false) String reviewType,
            @RequestParam(required = false) String moduleCode,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate periodStart,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate periodEnd) {
        return ApiResponse.success(reviewService.list(new ReviewFilter(reviewType, moduleCode, periodStart, periodEnd)));
    }

    @PostMapping
    public ApiResponse<ReviewItem> create(@Valid @RequestBody CreateReviewRequest request) {
        return ApiResponse.success(reviewService.create(request));
    }

    @PutMapping("/{id}")
    public ApiResponse<ReviewItem> update(@PathVariable long id, @Valid @RequestBody CreateReviewRequest request) {
        return ApiResponse.success(reviewService.update(id, request));
    }

    @DeleteMapping("/{id}")
    public ApiResponse<Void> delete(@PathVariable long id) {
        reviewService.delete(id);
        return ApiResponse.success();
    }
}
