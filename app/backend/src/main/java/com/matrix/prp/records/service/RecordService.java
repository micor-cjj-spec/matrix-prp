package com.matrix.prp.records.service;

import com.matrix.prp.records.model.CreateRecordRequest;
import com.matrix.prp.records.model.RecordFilter;
import com.matrix.prp.records.model.RecordItem;
import com.matrix.prp.records.repository.RecordRepository;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class RecordService {

    private final RecordRepository recordRepository;

    public RecordService(RecordRepository recordRepository) {
        this.recordRepository = recordRepository;
    }

    public List<RecordItem> list() {
        return recordRepository.list();
    }

    public List<RecordItem> list(RecordFilter filter) {
        return recordRepository.list(filter == null ? new RecordFilter(null, null, null, null) : filter);
    }

    public RecordItem create(CreateRecordRequest request) {
        return recordRepository.create(request);
    }

    public RecordItem update(long id, CreateRecordRequest request) {
        return recordRepository.update(id, request);
    }

    public void delete(long id) {
        recordRepository.delete(id);
    }

    public int count() {
        return recordRepository.count();
    }
}
