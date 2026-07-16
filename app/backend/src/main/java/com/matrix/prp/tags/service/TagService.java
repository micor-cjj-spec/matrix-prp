package com.matrix.prp.tags.service;

import com.matrix.prp.tags.model.CreateTagRequest;
import com.matrix.prp.tags.model.TagItem;
import com.matrix.prp.tags.model.UpdateTagRequest;
import com.matrix.prp.tags.repository.TagRepository;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class TagService {

    private final TagRepository tagRepository;

    public TagService(TagRepository tagRepository) {
        this.tagRepository = tagRepository;
    }

    public List<TagItem> list() {
        return tagRepository.list();
    }

    public TagItem create(CreateTagRequest request) {
        return tagRepository.create(request);
    }

    public TagItem update(long id, UpdateTagRequest request) {
        return tagRepository.update(id, request);
    }

    public void delete(long id) {
        tagRepository.delete(id);
    }
}
