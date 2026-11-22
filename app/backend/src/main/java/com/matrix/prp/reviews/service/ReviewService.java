package com.matrix.prp.reviews.service;

import com.matrix.prp.reviews.model.CreateReviewRequest;
import com.matrix.prp.reviews.model.ReviewFilter;
import com.matrix.prp.reviews.model.ReviewItem;
import com.matrix.prp.reviews.repository.ReviewRepository;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class ReviewService {

    private final ReviewRepository reviewRepository;

    public ReviewService(ReviewRepository reviewRepository) {
        this.reviewRepository = reviewRepository;
    }

    public List<ReviewItem> list() {
        return reviewRepository.list();
    }

    public List<ReviewItem> list(ReviewFilter filter) {
        return reviewRepository.list(filter);
    }

    /** Separate bounded read path for MCP; REST list remains unchanged. */
    public List<ReviewItem> listLimited(ReviewFilter filter, int limit) {
        if (limit < 1 || limit > 20) throw new IllegalArgumentException("Review limit must be 1..20");
        return reviewRepository.listLimited(filter, limit);
    }

    public ReviewItem create(CreateReviewRequest request) {
        return reviewRepository.create(request);
    }

    public ReviewItem update(long id, CreateReviewRequest request) {
        return reviewRepository.update(id, request);
    }

    public void delete(long id) {
        reviewRepository.delete(id);
    }
}
