package com.matrix.prp.reviews.repository;

import com.matrix.prp.reviews.model.CreateReviewRequest;
import com.matrix.prp.reviews.model.ReviewFilter;
import com.matrix.prp.reviews.model.ReviewItem;
import java.util.List;

public interface ReviewRepository {

    List<ReviewItem> list();

    List<ReviewItem> list(ReviewFilter filter);

    /** Database-bounded owner-scoped query for MCP previews, limit 1..20. */
    List<ReviewItem> listLimited(ReviewFilter filter, int limit);

    ReviewItem create(CreateReviewRequest request);

    ReviewItem update(long id, CreateReviewRequest request);

    void delete(long id);
}
