package com.matrix.prp.tags.repository;

import com.matrix.prp.common.api.ResourceNotFoundException;
import com.matrix.prp.auth.security.TestTenant;
import java.util.concurrent.ConcurrentHashMap;
import com.matrix.prp.tags.model.CreateTagRequest;
import com.matrix.prp.tags.model.TagItem;
import com.matrix.prp.tags.model.UpdateTagRequest;
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
public class InMemoryTagRepository implements TagRepository {

    private final AtomicLong idGenerator = new AtomicLong(5000);
    private final CopyOnWriteArrayList<TagItem> tags = new CopyOnWriteArrayList<>();
    private final Map<Long,Long> owners = new ConcurrentHashMap<>();

    @Override
    public List<TagItem> list() {
        return tags.stream()
                .filter(item -> java.util.Objects.equals(owners.get(item.id()), TestTenant.id()))
                .sorted(Comparator.comparing(TagItem::createdAt).reversed())
                .toList();
    }

    @Override
    public TagItem create(CreateTagRequest request) {
        TagItem tag = new TagItem(
                idGenerator.incrementAndGet(),
                request.name(),
                request.color() == null ? "#1d4ed8" : request.color(),
                request.description() == null ? "" : request.description(),
                OffsetDateTime.now());
        tags.add(tag);
        owners.put(tag.id(), TestTenant.id());
        return tag;
    }

    @Override
    public TagItem update(long id, UpdateTagRequest request) {
        TagItem existing = findById(id);
        TagItem updated = new TagItem(
                existing.id(),
                request.name(),
                request.color() == null ? "#1d4ed8" : request.color(),
                request.description() == null ? "" : request.description(),
                existing.createdAt());
        tags.remove(existing);
        tags.add(updated);
        return updated;
    }

    @Override
    public void delete(long id) {
        boolean removed = tags.removeIf(tag -> tag.id() == id && java.util.Objects.equals(owners.get(id), TestTenant.id()));
        if (!removed) {
            throw new ResourceNotFoundException("Tag not found: " + id);
        }
    }

    private TagItem findById(long id) {
        return tags.stream()
                .filter(tag -> tag.id() == id && java.util.Objects.equals(owners.get(id), TestTenant.id()))
                .findFirst()
                .orElseThrow(() -> new ResourceNotFoundException("Tag not found: " + id));
    }
}
