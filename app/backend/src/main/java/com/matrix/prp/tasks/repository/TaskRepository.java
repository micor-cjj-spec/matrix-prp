package com.matrix.prp.tasks.repository;

import com.matrix.prp.tasks.model.CreateTaskRequest;
import com.matrix.prp.tasks.model.TaskFilter;
import com.matrix.prp.tasks.model.TaskItem;
import java.util.List;

public interface TaskRepository {

    TaskItem get(long id);

    List<TaskItem> list();

    List<TaskItem> list(TaskFilter filter);

    /** Safe generic fallback for test repositories; the MyBatis implementation uses SQL LIMIT. */
    default List<TaskItem> listLimited(TaskFilter filter, int limit) {
        if (limit < 1 || limit > 100) throw new IllegalArgumentException("Limit out of range");
        return list(filter).stream().limit(limit).toList();
    }

    TaskItem create(CreateTaskRequest request);

    TaskItem update(long id, CreateTaskRequest request);

    TaskItem updateStatus(long id, String status);

    void delete(long id);

}
