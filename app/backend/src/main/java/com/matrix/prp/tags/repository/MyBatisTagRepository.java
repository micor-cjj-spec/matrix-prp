package com.matrix.prp.tags.repository;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.common.api.ResourceNotFoundException;
import com.matrix.prp.tags.entity.TagEntity;
import com.matrix.prp.tags.mapper.TagMapper;
import com.matrix.prp.tags.model.CreateTagRequest;
import com.matrix.prp.tags.model.TagItem;
import com.matrix.prp.tags.model.UpdateTagRequest;
import java.time.LocalDateTime;
import java.util.List;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;

@Repository
@Profile("!test")
public class MyBatisTagRepository implements TagRepository {

    private final TagMapper tagMapper;

    public MyBatisTagRepository(TagMapper tagMapper) {
        this.tagMapper = tagMapper;
    }

    @Override
    public List<TagItem> list() {
        return tagMapper.selectList(new LambdaQueryWrapper<TagEntity>()
                        .eq(TagEntity::getUserId, CurrentUser.id())
                        .orderByDesc(TagEntity::getCreatedAt))
                .stream()
                .map(TagEntity::toItem)
                .toList();
    }

    @Override
    public TagItem create(CreateTagRequest request) {
        LocalDateTime now = LocalDateTime.now();
        TagEntity entity = new TagEntity();
        entity.setUserId(CurrentUser.id());
        entity.setName(request.name());
        entity.setColor(request.color() == null ? "#1d4ed8" : request.color());
        entity.setDescription(request.description() == null ? "" : request.description());
        entity.setCreatedAt(now);
        entity.setUpdatedAt(now);
        entity.setDeleted(0);
        tagMapper.insert(entity);
        return entity.toItem();
    }

    @Override
    public TagItem update(long id, UpdateTagRequest request) {
        TagEntity entity = findById(id);
        entity.setName(request.name());
        entity.setColor(request.color() == null ? "#1d4ed8" : request.color());
        entity.setDescription(request.description() == null ? "" : request.description());
        entity.setUpdatedAt(LocalDateTime.now());
        tagMapper.updateById(entity);
        return entity.toItem();
    }

    @Override
    public void delete(long id) {
        findById(id);
        int deleted = tagMapper.deleteById(id);
        if (deleted == 0) {
            throw new ResourceNotFoundException("Tag not found: " + id);
        }
    }

    private TagEntity findById(long id) {
        TagEntity entity = tagMapper.selectById(id);
        if (entity == null || !java.util.Objects.equals(entity.getUserId(), CurrentUser.id())) {
            throw new ResourceNotFoundException("Tag not found: " + id);
        }
        return entity;
    }
}
