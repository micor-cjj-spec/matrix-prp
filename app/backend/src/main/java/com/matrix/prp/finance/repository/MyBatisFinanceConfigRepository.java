package com.matrix.prp.finance.repository;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.matrix.prp.common.api.ResourceNotFoundException;
import com.matrix.prp.finance.entity.FinanceAccountEntity;
import com.matrix.prp.finance.entity.FinanceCategoryEntity;
import com.matrix.prp.finance.mapper.FinanceAccountMapper;
import com.matrix.prp.finance.mapper.FinanceCategoryMapper;
import com.matrix.prp.finance.model.CreateFinanceAccountRequest;
import com.matrix.prp.finance.model.CreateFinanceCategoryRequest;
import com.matrix.prp.finance.model.FinanceAccountItem;
import com.matrix.prp.finance.model.FinanceCategoryItem;
import java.time.LocalDateTime;
import java.util.List;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;

@Repository
@Profile("!test")
public class MyBatisFinanceConfigRepository implements FinanceConfigRepository {

    private static final long DEFAULT_USER_ID = 1L;

    private final FinanceAccountMapper accountMapper;
    private final FinanceCategoryMapper categoryMapper;

    public MyBatisFinanceConfigRepository(FinanceAccountMapper accountMapper, FinanceCategoryMapper categoryMapper) {
        this.accountMapper = accountMapper;
        this.categoryMapper = categoryMapper;
    }

    @Override
    public List<FinanceAccountItem> listAccounts() {
        return accountMapper.selectList(new LambdaQueryWrapper<FinanceAccountEntity>()
                        .orderByDesc(FinanceAccountEntity::getCreatedAt))
                .stream()
                .map(FinanceAccountEntity::toItem)
                .toList();
    }

    @Override
    public FinanceAccountItem createAccount(CreateFinanceAccountRequest request) {
        LocalDateTime now = LocalDateTime.now();
        FinanceAccountEntity entity = new FinanceAccountEntity();
        applyAccountRequest(entity, request);
        entity.setUserId(DEFAULT_USER_ID);
        entity.setCreatedAt(now);
        entity.setUpdatedAt(now);
        entity.setDeleted(0);
        accountMapper.insert(entity);
        return entity.toItem();
    }

    @Override
    public FinanceAccountItem updateAccount(long id, CreateFinanceAccountRequest request) {
        FinanceAccountEntity entity = findAccount(id);
        applyAccountRequest(entity, request);
        entity.setUpdatedAt(LocalDateTime.now());
        accountMapper.updateById(entity);
        return entity.toItem();
    }

    @Override
    public void deleteAccount(long id) {
        int deleted = accountMapper.deleteById(id);
        if (deleted == 0) {
            throw new ResourceNotFoundException("Finance account not found: " + id);
        }
    }

    @Override
    public List<FinanceCategoryItem> listCategories(String type) {
        LambdaQueryWrapper<FinanceCategoryEntity> query = new LambdaQueryWrapper<FinanceCategoryEntity>()
                .orderByDesc(FinanceCategoryEntity::getCreatedAt);
        if (type != null && !type.isBlank()) {
            query.eq(FinanceCategoryEntity::getType, type);
        }
        return categoryMapper.selectList(query)
                .stream()
                .map(FinanceCategoryEntity::toItem)
                .toList();
    }

    @Override
    public FinanceCategoryItem createCategory(CreateFinanceCategoryRequest request) {
        LocalDateTime now = LocalDateTime.now();
        FinanceCategoryEntity entity = new FinanceCategoryEntity();
        applyCategoryRequest(entity, request);
        entity.setUserId(DEFAULT_USER_ID);
        entity.setCreatedAt(now);
        entity.setUpdatedAt(now);
        entity.setDeleted(0);
        categoryMapper.insert(entity);
        return entity.toItem();
    }

    @Override
    public FinanceCategoryItem updateCategory(long id, CreateFinanceCategoryRequest request) {
        FinanceCategoryEntity entity = findCategory(id);
        applyCategoryRequest(entity, request);
        entity.setUpdatedAt(LocalDateTime.now());
        categoryMapper.updateById(entity);
        return entity.toItem();
    }

    @Override
    public void deleteCategory(long id) {
        int deleted = categoryMapper.deleteById(id);
        if (deleted == 0) {
            throw new ResourceNotFoundException("Finance category not found: " + id);
        }
    }

    private FinanceAccountEntity findAccount(long id) {
        FinanceAccountEntity entity = accountMapper.selectById(id);
        if (entity == null) {
            throw new ResourceNotFoundException("Finance account not found: " + id);
        }
        return entity;
    }

    private FinanceCategoryEntity findCategory(long id) {
        FinanceCategoryEntity entity = categoryMapper.selectById(id);
        if (entity == null) {
            throw new ResourceNotFoundException("Finance category not found: " + id);
        }
        return entity;
    }

    private void applyAccountRequest(FinanceAccountEntity entity, CreateFinanceAccountRequest request) {
        entity.setName(request.name());
        entity.setType(request.type() == null || request.type().isBlank() ? "cash" : request.type());
        entity.setCurrency(request.currency() == null || request.currency().isBlank() ? "CNY" : request.currency());
        entity.setOpeningBalance(request.openingBalance());
        entity.setNote(request.note() == null ? "" : request.note());
    }

    private void applyCategoryRequest(FinanceCategoryEntity entity, CreateFinanceCategoryRequest request) {
        entity.setName(request.name());
        entity.setType(request.type());
        entity.setColor(request.color() == null || request.color().isBlank() ? "#2563eb" : request.color());
        entity.setNote(request.note() == null ? "" : request.note());
    }
}
