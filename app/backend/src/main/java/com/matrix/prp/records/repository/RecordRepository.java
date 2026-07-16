package com.matrix.prp.records.repository;

import com.matrix.prp.records.model.CreateRecordRequest;
import com.matrix.prp.records.model.RecordFilter;
import com.matrix.prp.records.model.RecordItem;
import java.util.List;

public interface RecordRepository {

    List<RecordItem> list();

    List<RecordItem> list(RecordFilter filter);

    RecordItem create(CreateRecordRequest request);

    RecordItem update(long id, CreateRecordRequest request);

    void delete(long id);

    int count();
}
