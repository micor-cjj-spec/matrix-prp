package com.matrix.prp.records.repository;

import com.matrix.prp.records.model.CreateRecordRequest;
import com.matrix.prp.records.model.RecordFilter;
import com.matrix.prp.records.model.RecordItem;
import java.util.List;

public interface RecordRepository {

    List<RecordItem> list();

    List<RecordItem> list(RecordFilter filter);

    /** Bounded owner-scoped retrieval; persistent implementation limits before materializing rows. */
    default List<RecordItem> listLimited(RecordFilter filter, int limit) {
        if (limit < 1 || limit > 100) throw new IllegalArgumentException("Limit out of range");
        return list(filter).stream().limit(limit).toList();
    }

    RecordItem create(CreateRecordRequest request);

    RecordItem update(long id, CreateRecordRequest request);

    void delete(long id);

    int count();
}
