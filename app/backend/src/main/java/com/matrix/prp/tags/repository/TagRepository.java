package com.matrix.prp.tags.repository;

import com.matrix.prp.tags.model.CreateTagRequest;
import com.matrix.prp.tags.model.TagItem;
import com.matrix.prp.tags.model.UpdateTagRequest;
import java.util.List;

public interface TagRepository {

    List<TagItem> list();

    TagItem create(CreateTagRequest request);

    TagItem update(long id, UpdateTagRequest request);

    void delete(long id);
}
