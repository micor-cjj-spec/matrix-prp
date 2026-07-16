package com.matrix.prp.tags.api;

import com.matrix.prp.common.api.ApiResponse;
import com.matrix.prp.tags.model.CreateTagRequest;
import com.matrix.prp.tags.model.TagItem;
import com.matrix.prp.tags.model.UpdateTagRequest;
import com.matrix.prp.tags.service.TagService;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tags")
public class TagController {

    private final TagService tagService;

    public TagController(TagService tagService) {
        this.tagService = tagService;
    }

    @GetMapping
    public ApiResponse<List<TagItem>> list() {
        return ApiResponse.success(tagService.list());
    }

    @PostMapping
    public ApiResponse<TagItem> create(@Valid @RequestBody CreateTagRequest request) {
        return ApiResponse.success(tagService.create(request));
    }

    @PutMapping("/{id}")
    public ApiResponse<TagItem> update(@PathVariable long id, @Valid @RequestBody UpdateTagRequest request) {
        return ApiResponse.success(tagService.update(id, request));
    }

    @DeleteMapping("/{id}")
    public ApiResponse<Void> delete(@PathVariable long id) {
        tagService.delete(id);
        return ApiResponse.success();
    }
}
