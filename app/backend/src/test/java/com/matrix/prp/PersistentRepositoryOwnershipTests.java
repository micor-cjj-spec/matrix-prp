package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.common.api.ResourceNotFoundException;
import com.matrix.prp.tasks.entity.TaskEntity;
import com.matrix.prp.tasks.mapper.TaskMapper;
import com.matrix.prp.tasks.repository.MyBatisTaskRepository;
import com.matrix.prp.finance.entity.FinanceTransactionEntity;
import com.matrix.prp.finance.mapper.FinanceTransactionMapper;
import com.matrix.prp.finance.repository.MyBatisFinanceRepository;
import com.matrix.prp.records.entity.RecordEntity;
import com.matrix.prp.records.mapper.RecordMapper;
import com.matrix.prp.records.mapper.RecordTagMapper;
import com.matrix.prp.records.repository.MyBatisRecordRepository;
import com.matrix.prp.tags.mapper.TagMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

class PersistentRepositoryOwnershipTests {
    private void asUser(long id) {
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken(
                        new UserProfile(id, "user" + id, "User " + id), null,
                        java.util.List.of()));
    }

    @AfterEach
    void clear() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void taskStatusCannotBeChangedByAnotherUserEvenWithKnownId() {
        asUser(2);
        TaskMapper mapper = mock(TaskMapper.class);
        TaskEntity entity = new TaskEntity();
        entity.setUserId(1L);
        when(mapper.selectById(77L)).thenReturn(entity);
        assertThatThrownBy(() -> new MyBatisTaskRepository(mapper).updateStatus(77L, "done"))
                .isInstanceOf(ResourceNotFoundException.class);
        verify(mapper, never()).updateById(any(TaskEntity.class));
    }

    @Test
    void financeTransactionCannotBeDeletedByAnotherUser() {
        asUser(2);
        FinanceTransactionMapper mapper = mock(FinanceTransactionMapper.class);
        FinanceTransactionEntity entity = new FinanceTransactionEntity();
        entity.setUserId(1L);
        when(mapper.selectById(31L)).thenReturn(entity);
        assertThatThrownBy(() -> new MyBatisFinanceRepository(mapper, mock(com.matrix.prp.finance.mapper.FinanceAccountMapper.class)).deleteTransaction(31L))
                .isInstanceOf(ResourceNotFoundException.class);
        verify(mapper, never()).deleteById(31L);
    }

    @Test
    void recordCannotBeDeletedByAnotherUser() {
        asUser(2);
        RecordMapper records = mock(RecordMapper.class);
        RecordTagMapper links = mock(RecordTagMapper.class);
        TagMapper tags = mock(TagMapper.class);
        RecordEntity record = new RecordEntity();
        record.setUserId(1L);
        when(records.selectById(22L)).thenReturn(record);
        assertThatThrownBy(() -> new MyBatisRecordRepository(records, links, tags).delete(22L))
                .isInstanceOf(ResourceNotFoundException.class);
        verify(records, never()).deleteById(22L);
    }
    @Test
    void financeCategoryCannotBeDeletedByAnotherUser() {
        asUser(2);
        com.matrix.prp.finance.mapper.FinanceAccountMapper accounts =
                mock(com.matrix.prp.finance.mapper.FinanceAccountMapper.class);
        com.matrix.prp.finance.mapper.FinanceCategoryMapper categories =
                mock(com.matrix.prp.finance.mapper.FinanceCategoryMapper.class);
        com.matrix.prp.finance.entity.FinanceCategoryEntity entity =
                new com.matrix.prp.finance.entity.FinanceCategoryEntity();
        entity.setUserId(1L);
        when(categories.selectById(88L)).thenReturn(entity);
        assertThatThrownBy(() -> new com.matrix.prp.finance.repository.MyBatisFinanceConfigRepository(
                accounts, categories, mock(com.matrix.prp.finance.mapper.FinanceTransactionMapper.class),
                mock(com.matrix.prp.finance.mapper.FinanceTransferMapper.class)).deleteCategory(88L))
                .isInstanceOf(ResourceNotFoundException.class);
        verify(categories, never()).deleteById(88L);
    }

}
