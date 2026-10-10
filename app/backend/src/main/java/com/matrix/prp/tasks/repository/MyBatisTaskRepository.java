package com.matrix.prp.tasks.repository;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.common.api.ResourceNotFoundException;
import com.matrix.prp.tasks.entity.TaskEntity;
import com.matrix.prp.tasks.mapper.TaskMapper;
import com.matrix.prp.tasks.model.CreateTaskRequest;
import com.matrix.prp.tasks.model.TaskFilter;
import com.matrix.prp.tasks.model.TaskItem;
import java.time.LocalDateTime;
import java.util.List;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;

@Repository
@Profile("!test")
public class MyBatisTaskRepository implements TaskRepository {

    private final TaskMapper taskMapper;

    public MyBatisTaskRepository(TaskMapper taskMapper) {
        this.taskMapper = taskMapper;
    }

    @Override
    public List<TaskItem> list() {
        return list(new TaskFilter(null, null, null, null));
    }

    @Override
    public List<TaskItem> list(TaskFilter filter) {
        return taskMapper.selectList(buildFilterQuery(filter)
                        .orderByDesc(TaskEntity::getCreatedAt))
                .stream()
                .map(TaskEntity::toItem)
                .toList();
    }

    @Override
    public TaskItem create(CreateTaskRequest request) {
        LocalDateTime now = LocalDateTime.now();
        TaskEntity entity = new TaskEntity();
        entity.setUserId(CurrentUser.id());
        entity.setModuleCode(request.moduleCode());
        entity.setTitle(request.title());
        entity.setDescription(request.description() == null ? "" : request.description());
        entity.setPriority(request.priority() == null ? "medium" : request.priority());
        entity.setStatus("todo");
        entity.setDueDate(request.dueDate());
        entity.setCreatedAt(now);
        entity.setUpdatedAt(now);
        entity.setDeleted(0);
        taskMapper.insert(entity);
        return entity.toItem();
    }

    @Override
    public TaskItem update(long id, CreateTaskRequest request) {
        TaskEntity entity = findById(id);
        LocalDateTime now = LocalDateTime.now();
        entity.setModuleCode(request.moduleCode());
        entity.setTitle(request.title());
        entity.setDescription(request.description() == null ? "" : request.description());
        entity.setPriority(request.priority() == null ? "medium" : request.priority());
        entity.setDueDate(request.dueDate());
        entity.setUpdatedAt(now);
        taskMapper.updateById(entity);
        return entity.toItem();
    }

    @Override
    public TaskItem updateStatus(long id, String status) {
        TaskEntity entity = findById(id);
        LocalDateTime now = LocalDateTime.now();
        entity.setStatus(status);
        entity.setCompletedAt("done".equals(status) ? now : null);
        entity.setUpdatedAt(now);
        taskMapper.updateById(entity);
        return entity.toItem();
    }

    @Override
    public void delete(long id) {
        findById(id);
        taskMapper.deleteById(id);
    }


    private TaskEntity findById(long id) {
        TaskEntity entity = taskMapper.selectById(id);
        if (entity == null || !java.util.Objects.equals(entity.getUserId(), CurrentUser.id())) {
            throw new ResourceNotFoundException("Task not found: " + id);
        }
        return entity;
    }

    private LambdaQueryWrapper<TaskEntity> buildFilterQuery(TaskFilter filter) {
        TaskFilter effectiveFilter = filter == null ? new TaskFilter(null, null, null, null) : filter;
        LambdaQueryWrapper<TaskEntity> query = new LambdaQueryWrapper<TaskEntity>()
                .eq(TaskEntity::getUserId, CurrentUser.id());
        if (effectiveFilter.status() != null && !effectiveFilter.status().isBlank()) {
            query.eq(TaskEntity::getStatus, effectiveFilter.status());
        }
        if (effectiveFilter.moduleCode() != null && !effectiveFilter.moduleCode().isBlank()) {
            query.eq(TaskEntity::getModuleCode, effectiveFilter.moduleCode());
        }
        if (effectiveFilter.dueDate() != null) {
            query.eq(TaskEntity::getDueDate, effectiveFilter.dueDate());
        }
        if (effectiveFilter.priority() != null && !effectiveFilter.priority().isBlank()) {
            query.eq(TaskEntity::getPriority, effectiveFilter.priority());
        }
        return query;
    }
}
