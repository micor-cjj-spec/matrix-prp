package com.matrix.prp.reviews.repository;

import com.matrix.prp.common.api.ResourceNotFoundException;
import com.matrix.prp.auth.security.TestTenant;
import java.util.concurrent.ConcurrentHashMap;
import com.matrix.prp.reviews.model.CreateReviewRequest;
import com.matrix.prp.reviews.model.ReviewFilter;
import com.matrix.prp.reviews.model.ReviewItem;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;

@Repository
@Profile("test")
public class InMemoryReviewRepository implements ReviewRepository {

    private final AtomicLong idGenerator = new AtomicLong(4000);
    private final CopyOnWriteArrayList<ReviewItem> reviews = new CopyOnWriteArrayList<>();
    private final Map<Long,Long> owners = new ConcurrentHashMap<>();

    @Override
    public List<ReviewItem> list() {
        return list(new ReviewFilter(null, null, null, null));
    }

    @Override
    public List<ReviewItem> list(ReviewFilter filter) {
        ReviewFilter effectiveFilter = filter == null ? new ReviewFilter(null, null, null, null) : filter;
        return reviews.stream()
                .filter(item -> java.util.Objects.equals(owners.get(item.id()), TestTenant.id()))
                .filter(review -> effectiveFilter.reviewType() == null || effectiveFilter.reviewType().isBlank()
                        || effectiveFilter.reviewType().equals(review.reviewType()))
                .filter(review -> effectiveFilter.moduleCode() == null || effectiveFilter.moduleCode().isBlank()
                        || effectiveFilter.moduleCode().equals(review.moduleCode()))
                .filter(review -> effectiveFilter.periodStart() == null
                        || !review.periodEnd().isBefore(effectiveFilter.periodStart()))
                .filter(review -> effectiveFilter.periodEnd() == null
                        || !review.periodStart().isAfter(effectiveFilter.periodEnd()))
                .sorted(Comparator.comparing(ReviewItem::createdAt).reversed())
                .toList();
    }

    @Override
    public ReviewItem create(CreateReviewRequest request) {
        LocalDate today = LocalDate.now();
        ReviewItem review = new ReviewItem(
                idGenerator.incrementAndGet(),
                request.reviewType(),
                request.moduleCode(),
                request.title(),
                request.summary() == null ? "" : request.summary(),
                request.highlights() == null ? "" : request.highlights(),
                request.problems() == null ? "" : request.problems(),
                request.nextActions() == null ? "" : request.nextActions(),
                request.periodStart() == null ? today : request.periodStart(),
                request.periodEnd() == null ? today : request.periodEnd(),
                OffsetDateTime.now());
        reviews.add(review);
        owners.put(review.id(), TestTenant.id());
        return review;
    }

    @Override
    public ReviewItem update(long id, CreateReviewRequest request) {
        ReviewItem existing = findById(id);
        LocalDate today = LocalDate.now();
        ReviewItem updated = new ReviewItem(
                existing.id(),
                request.reviewType(),
                request.moduleCode(),
                request.title(),
                request.summary() == null ? "" : request.summary(),
                request.highlights() == null ? "" : request.highlights(),
                request.problems() == null ? "" : request.problems(),
                request.nextActions() == null ? "" : request.nextActions(),
                request.periodStart() == null ? today : request.periodStart(),
                request.periodEnd() == null ? today : request.periodEnd(),
                existing.createdAt());
        reviews.remove(existing);
        reviews.add(updated);
        return updated;
    }

    @Override
    public void delete(long id) {
        boolean removed = reviews.removeIf(review -> review.id() == id && java.util.Objects.equals(owners.get(id), TestTenant.id()));
        if (!removed) {
            throw new ResourceNotFoundException("Review not found: " + id);
        }
    }

    private ReviewItem findById(long id) {
        return reviews.stream()
                .filter(review -> review.id() == id && java.util.Objects.equals(owners.get(id), TestTenant.id()))
                .findFirst()
                .orElseThrow(() -> new ResourceNotFoundException("Review not found: " + id));
    }
}
