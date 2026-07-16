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
