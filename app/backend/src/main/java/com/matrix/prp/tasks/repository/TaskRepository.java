package com.matrix.prp.tasks.repository;

import com.matrix.prp.tasks.model.CreateTaskRequest;
import com.matrix.prp.tasks.model.TaskFilter;
import com.matrix.prp.tasks.model.TaskItem;
import java.util.List;

public interface TaskRepository {

    List<TaskItem> list();

    List<TaskItem> list(TaskFilter filter);

    TaskItem create(CreateTaskRequest request);

    TaskItem update(long id, CreateTaskRequest request);

    TaskItem updateStatus(long id, String status);

    void delete(long id);

}
