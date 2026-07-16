package com.matrix.prp.records.repository;

import com.matrix.prp.common.api.ResourceNotFoundException;
import com.matrix.prp.records.model.CreateRecordRequest;
import com.matrix.prp.records.model.RecordFilter;
import com.matrix.prp.records.model.RecordItem;
import com.matrix.prp.records.model.RecordTagItem;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;

@Repository
@Profile("test")
public class InMemoryRecordRepository implements RecordRepository {

    private final AtomicLong idGenerator = new AtomicLong(1000);
    private final CopyOnWriteArrayList<RecordItem> records = new CopyOnWriteArrayList<>();

    @Override
    public List<RecordItem> list() {
        return list(new RecordFilter(null, null, null, null));
    }

    @Override
    public List<RecordItem> list(RecordFilter filter) {
        RecordFilter effectiveFilter = filter == null ? new RecordFilter(null, null, null, null) : filter;
        return records.stream()
                .filter(record -> effectiveFilter.moduleCode() == null || effectiveFilter.moduleCode().isBlank()
                        || effectiveFilter.moduleCode().equals(record.moduleCode()))
                .filter(record -> effectiveFilter.tagId() == null
                        || record.tags().stream().anyMatch(tag -> tag.id() == effectiveFilter.tagId()))
                .filter(record -> effectiveFilter.recordDate() == null
                        || effectiveFilter.recordDate().equals(record.recordDate()))
                .filter(record -> matchesKeyword(record, effectiveFilter.keyword()))
                .sorted(Comparator.comparing(RecordItem::createdAt).reversed())
                .toList();
    }

    @Override
    public RecordItem create(CreateRecordRequest request) {
        RecordItem record = new RecordItem(
                idGenerator.incrementAndGet(),
                request.moduleCode(),
                request.title(),
                request.content() == null ? "" : request.content(),
                request.recordDate() == null ? LocalDate.now() : request.recordDate(),
                OffsetDateTime.now(),
                toTagItems(request.tagIds()));
        records.add(record);
        return record;
    }

    @Override
    public RecordItem update(long id, CreateRecordRequest request) {
        RecordItem existing = records.stream()
                .filter(record -> record.id() == id)
                .findFirst()
                .orElseThrow(() -> new ResourceNotFoundException("Record not found: " + id));
        RecordItem updated = new RecordItem(
                existing.id(),
                request.moduleCode(),
                request.title(),
                request.content() == null ? "" : request.content(),
                request.recordDate() == null ? LocalDate.now() : request.recordDate(),
                existing.createdAt(),
                toTagItems(request.tagIds()));
        records.remove(existing);
        records.add(updated);
        return updated;
    }

    @Override
    public void delete(long id) {
        boolean removed = records.removeIf(record -> record.id() == id);
        if (!removed) {
            throw new ResourceNotFoundException("Record not found: " + id);
        }
    }

    @Override
    public int count() {
        return records.size();
    }

    private List<RecordTagItem> toTagItems(List<Long> tagIds) {
        if (tagIds == null) {
            return List.of();
        }
        return tagIds.stream()
                .map(id -> new RecordTagItem(id, "tag-" + id, "#1d4ed8"))
                .toList();
    }

    private boolean matchesKeyword(RecordItem record, String keyword) {
        if (keyword == null || keyword.isBlank()) {
            return true;
        }
        String normalized = keyword.toLowerCase();
        return record.title().toLowerCase().contains(normalized)
                || record.content().toLowerCase().contains(normalized);
    }
}
