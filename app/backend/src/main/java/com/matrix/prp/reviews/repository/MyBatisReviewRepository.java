package com.matrix.prp.reviews.repository;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.matrix.prp.common.api.ResourceNotFoundException;
import com.matrix.prp.reviews.entity.ReviewEntity;
import com.matrix.prp.reviews.mapper.ReviewMapper;
import com.matrix.prp.reviews.model.CreateReviewRequest;
import com.matrix.prp.reviews.model.ReviewFilter;
import com.matrix.prp.reviews.model.ReviewItem;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;

@Repository
@Profile("!test")
public class MyBatisReviewRepository implements ReviewRepository {

    private static final long DEFAULT_USER_ID = 1L;

    private final ReviewMapper reviewMapper;

    public MyBatisReviewRepository(ReviewMapper reviewMapper) {
        this.reviewMapper = reviewMapper;
    }

    @Override
    public List<ReviewItem> list() {
        return list(new ReviewFilter(null, null, null, null));
    }

    @Override
    public List<ReviewItem> list(ReviewFilter filter) {
        ReviewFilter effectiveFilter = filter == null ? new ReviewFilter(null, null, null, null) : filter;
        LambdaQueryWrapper<ReviewEntity> wrapper = new LambdaQueryWrapper<ReviewEntity>()
                .eq(effectiveFilter.reviewType() != null && !effectiveFilter.reviewType().isBlank(),
                        ReviewEntity::getReviewType,
                        effectiveFilter.reviewType())
                .eq(effectiveFilter.moduleCode() != null && !effectiveFilter.moduleCode().isBlank(),
                        ReviewEntity::getModuleCode,
                        effectiveFilter.moduleCode())
                .ge(effectiveFilter.periodStart() != null,
                        ReviewEntity::getPeriodEnd,
                        effectiveFilter.periodStart())
                .le(effectiveFilter.periodEnd() != null,
                        ReviewEntity::getPeriodStart,
                        effectiveFilter.periodEnd())
                .orderByDesc(ReviewEntity::getCreatedAt);
        return reviewMapper.selectList(wrapper)
                .stream()
                .map(ReviewEntity::toItem)
                .toList();
    }

    @Override
    public ReviewItem create(CreateReviewRequest request) {
        LocalDate today = LocalDate.now();
        LocalDateTime now = LocalDateTime.now();
        ReviewEntity entity = new ReviewEntity();
        entity.setUserId(DEFAULT_USER_ID);
        entity.setReviewType(request.reviewType());
        entity.setModuleCode(request.moduleCode());
        entity.setTitle(request.title());
        entity.setSummary(request.summary() == null ? "" : request.summary());
        entity.setHighlights(request.highlights() == null ? "" : request.highlights());
        entity.setProblems(request.problems() == null ? "" : request.problems());
        entity.setNextActions(request.nextActions() == null ? "" : request.nextActions());
        entity.setPeriodStart(request.periodStart() == null ? today : request.periodStart());
        entity.setPeriodEnd(request.periodEnd() == null ? today : request.periodEnd());
        entity.setCreatedAt(now);
        entity.setUpdatedAt(now);
        entity.setDeleted(0);
        reviewMapper.insert(entity);
        return entity.toItem();
    }

    @Override
    public ReviewItem update(long id, CreateReviewRequest request) {
        ReviewEntity entity = findById(id);
        LocalDate today = LocalDate.now();
        entity.setReviewType(request.reviewType());
        entity.setModuleCode(request.moduleCode());
        entity.setTitle(request.title());
        entity.setSummary(request.summary() == null ? "" : request.summary());
        entity.setHighlights(request.highlights() == null ? "" : request.highlights());
        entity.setProblems(request.problems() == null ? "" : request.problems());
        entity.setNextActions(request.nextActions() == null ? "" : request.nextActions());
        entity.setPeriodStart(request.periodStart() == null ? today : request.periodStart());
        entity.setPeriodEnd(request.periodEnd() == null ? today : request.periodEnd());
        entity.setUpdatedAt(LocalDateTime.now());
        reviewMapper.updateById(entity);
        return entity.toItem();
    }

    @Override
    public void delete(long id) {
        findById(id);
        reviewMapper.deleteById(id);
    }

    private ReviewEntity findById(long id) {
        ReviewEntity entity = reviewMapper.selectById(id);
        if (entity == null) {
            throw new ResourceNotFoundException("Review not found: " + id);
        }
        return entity;
    }
}
