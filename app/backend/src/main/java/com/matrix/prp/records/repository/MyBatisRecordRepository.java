package com.matrix.prp.records.repository;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.matrix.prp.common.api.ResourceNotFoundException;
import com.matrix.prp.records.entity.RecordEntity;
import com.matrix.prp.records.entity.RecordTagEntity;
import com.matrix.prp.records.mapper.RecordMapper;
import com.matrix.prp.records.mapper.RecordTagMapper;
import com.matrix.prp.records.model.CreateRecordRequest;
import com.matrix.prp.records.model.RecordFilter;
import com.matrix.prp.records.model.RecordItem;
import com.matrix.prp.records.model.RecordTagItem;
import com.matrix.prp.tags.entity.TagEntity;
import com.matrix.prp.tags.mapper.TagMapper;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;

@Repository
@Profile("!test")
public class MyBatisRecordRepository implements RecordRepository {

    private static final long DEFAULT_USER_ID = 1L;

    private final RecordMapper recordMapper;
    private final RecordTagMapper recordTagMapper;
    private final TagMapper tagMapper;

    public MyBatisRecordRepository(RecordMapper recordMapper, RecordTagMapper recordTagMapper, TagMapper tagMapper) {
        this.recordMapper = recordMapper;
        this.recordTagMapper = recordTagMapper;
        this.tagMapper = tagMapper;
    }

    @Override
    public List<RecordItem> list() {
        return list(new RecordFilter(null, null, null, null));
    }

    @Override
    public List<RecordItem> list(RecordFilter filter) {
        RecordFilter effectiveFilter = filter == null ? new RecordFilter(null, null, null, null) : filter;
        List<Long> recordIds = findRecordIdsByTag(effectiveFilter.tagId());
        if (effectiveFilter.tagId() != null && recordIds.isEmpty()) {
            return List.of();
        }
        LambdaQueryWrapper<RecordEntity> query = new LambdaQueryWrapper<RecordEntity>()
                .orderByDesc(RecordEntity::getCreatedAt);
        if (effectiveFilter.moduleCode() != null && !effectiveFilter.moduleCode().isBlank()) {
            query.eq(RecordEntity::getModuleCode, effectiveFilter.moduleCode());
        }
        if (effectiveFilter.recordDate() != null) {
            query.eq(RecordEntity::getRecordDate, effectiveFilter.recordDate());
        }
        if (effectiveFilter.keyword() != null && !effectiveFilter.keyword().isBlank()) {
            query.and(wrapper -> wrapper.like(RecordEntity::getTitle, effectiveFilter.keyword())
                    .or()
                    .like(RecordEntity::getContent, effectiveFilter.keyword()));
        }
        if (effectiveFilter.tagId() != null) {
            query.in(RecordEntity::getId, recordIds);
        }
        List<RecordEntity> records = recordMapper.selectList(query);
        Map<Long, List<RecordTagItem>> tagsByRecordId = loadTagsByRecordId(records.stream()
                .map(RecordEntity::getId)
                .toList());
        return records.stream()
                .map(record -> record.toItem(tagsByRecordId.getOrDefault(record.getId(), List.of())))
                .toList();
    }

    @Override
    public RecordItem create(CreateRecordRequest request) {
        LocalDateTime now = LocalDateTime.now();
        RecordEntity entity = new RecordEntity();
        entity.setUserId(DEFAULT_USER_ID);
        entity.setModuleCode(request.moduleCode());
        entity.setTitle(request.title());
        entity.setContent(request.content() == null ? "" : request.content());
        entity.setRecordDate(request.recordDate() == null ? LocalDate.now() : request.recordDate());
        entity.setCreatedAt(now);
        entity.setUpdatedAt(now);
        entity.setDeleted(0);
        recordMapper.insert(entity);
        saveTagLinks(entity.getId(), request.tagIds(), now);
        return entity.toItem(loadTags(request.tagIds()));
    }

    @Override
    public RecordItem update(long id, CreateRecordRequest request) {
        RecordEntity entity = recordMapper.selectById(id);
        if (entity == null) {
            throw new ResourceNotFoundException("Record not found: " + id);
        }
        LocalDateTime now = LocalDateTime.now();
        entity.setModuleCode(request.moduleCode());
        entity.setTitle(request.title());
        entity.setContent(request.content() == null ? "" : request.content());
        entity.setRecordDate(request.recordDate() == null ? LocalDate.now() : request.recordDate());
        entity.setUpdatedAt(now);
        recordMapper.updateById(entity);
        replaceTagLinks(entity.getId(), request.tagIds(), now);
        return entity.toItem(loadTags(request.tagIds()));
    }

    @Override
    public void delete(long id) {
        RecordEntity entity = recordMapper.selectById(id);
        if (entity == null) {
            throw new ResourceNotFoundException("Record not found: " + id);
        }
        recordTagMapper.delete(new LambdaQueryWrapper<RecordTagEntity>()
                .eq(RecordTagEntity::getRecordId, id));
        recordMapper.deleteById(id);
    }

    @Override
    public int count() {
        return Math.toIntExact(recordMapper.selectCount(new LambdaQueryWrapper<>()));
    }

    private void saveTagLinks(Long recordId, List<Long> tagIds, LocalDateTime now) {
        if (tagIds == null || tagIds.isEmpty()) {
            return;
        }
        for (Long tagId : tagIds) {
            RecordTagEntity link = new RecordTagEntity();
            link.setRecordId(recordId);
            link.setTagId(tagId);
            link.setCreatedAt(now);
            recordTagMapper.insert(link);
        }
    }

    private void replaceTagLinks(Long recordId, List<Long> tagIds, LocalDateTime now) {
        recordTagMapper.delete(new LambdaQueryWrapper<RecordTagEntity>()
                .eq(RecordTagEntity::getRecordId, recordId));
        saveTagLinks(recordId, tagIds, now);
    }

    private List<Long> findRecordIdsByTag(Long tagId) {
        if (tagId == null) {
            return List.of();
        }
        return recordTagMapper.selectList(new LambdaQueryWrapper<RecordTagEntity>()
                        .eq(RecordTagEntity::getTagId, tagId))
                .stream()
                .map(RecordTagEntity::getRecordId)
                .distinct()
                .toList();
    }

    private Map<Long, List<RecordTagItem>> loadTagsByRecordId(List<Long> recordIds) {
        if (recordIds.isEmpty()) {
            return Map.of();
        }
        List<RecordTagEntity> links = recordTagMapper.selectList(new LambdaQueryWrapper<RecordTagEntity>()
                .in(RecordTagEntity::getRecordId, recordIds));
        if (links.isEmpty()) {
            return Map.of();
        }
        Map<Long, TagEntity> tagsById = tagMapper.selectBatchIds(links.stream()
                        .map(RecordTagEntity::getTagId)
                        .distinct()
                        .toList())
                .stream()
                .collect(Collectors.toMap(TagEntity::getId, tag -> tag));
        return links.stream()
                .filter(link -> tagsById.containsKey(link.getTagId()))
                .map(link -> Map.entry(link.getRecordId(), toRecordTagItem(tagsById.get(link.getTagId()))))
                .collect(Collectors.groupingBy(Map.Entry::getKey, Collectors.mapping(Map.Entry::getValue, Collectors.toList())));
    }

    private List<RecordTagItem> loadTags(List<Long> tagIds) {
        if (tagIds == null || tagIds.isEmpty()) {
            return List.of();
        }
        return tagMapper.selectBatchIds(tagIds).stream()
                .map(this::toRecordTagItem)
                .filter(tag -> tag != null)
                .toList();
    }

    private RecordTagItem toRecordTagItem(TagEntity tag) {
        if (tag == null) {
            return null;
        }
        return new RecordTagItem(tag.getId(), tag.getName(), tag.getColor());
    }
}
