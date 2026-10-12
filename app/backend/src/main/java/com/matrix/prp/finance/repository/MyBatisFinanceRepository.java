package com.matrix.prp.finance.repository;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.common.api.ResourceNotFoundException;
import com.matrix.prp.finance.entity.FinanceTransactionEntity;
import com.matrix.prp.finance.mapper.FinanceTransactionMapper;
import com.matrix.prp.finance.mapper.FinanceAccountMapper;
import com.matrix.prp.finance.entity.FinanceAccountEntity;
import org.springframework.transaction.annotation.Transactional;
import com.matrix.prp.finance.model.CreateFinanceTransactionRequest;
import com.matrix.prp.finance.model.FinanceAccountSummary;
import com.matrix.prp.finance.model.FinanceCategorySummary;
import com.matrix.prp.finance.model.FinanceMonthlySummary;
import com.matrix.prp.finance.model.FinanceTransactionFilter;
import com.matrix.prp.finance.model.FinanceTransactionItem;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.YearMonth;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;

@Repository
@Profile("!test")
public class MyBatisFinanceRepository implements FinanceRepository {

    private final FinanceTransactionMapper financeTransactionMapper;
    private final FinanceAccountMapper accountMapper;

    public MyBatisFinanceRepository(FinanceTransactionMapper financeTransactionMapper,
                                    FinanceAccountMapper accountMapper) {
        this.financeTransactionMapper = financeTransactionMapper;
        this.accountMapper = accountMapper;
    }

    /** Compatibility: old clients send a label, new rows also receive an immutable account ID. */
    private FinanceAccountEntity resolveAccount(String requested) {
        String name=requested==null || requested.isBlank() ? "default" : requested.trim();
        var query=new LambdaQueryWrapper<FinanceAccountEntity>()
                .eq(FinanceAccountEntity::getUserId,CurrentUser.id())
                .eq(FinanceAccountEntity::getName,name);
        var existing=accountMapper.selectList(query);
        if(!existing.isEmpty()) return existing.get(0);
        // Preserve legacy create-with-free-text account behavior, without orphaning a new row.
        FinanceAccountEntity a=new FinanceAccountEntity();
        a.setUserId(CurrentUser.id()); a.setName(name); a.setType("cash");
        a.setCurrency("CNY"); a.setOpeningBalance(BigDecimal.ZERO);
        a.setNote("通过记账自动创建，请核对期初余额");
        a.setCreatedAt(LocalDateTime.now()); a.setUpdatedAt(a.getCreatedAt()); a.setDeleted(0);
        try { accountMapper.insert(a); }
        catch (org.springframework.dao.DuplicateKeyException collision) {
            var concurrent=accountMapper.selectList(query);
            if(!concurrent.isEmpty()) return concurrent.get(0);
            throw collision;
        }
        return a;
    }

    @Override
    public List<FinanceTransactionItem> listTransactions() {
        return listTransactions(new FinanceTransactionFilter(null, null, null));
    }

    @Override
    public List<FinanceTransactionItem> listTransactions(FinanceTransactionFilter filter) {
        var names=accountMapper.selectList(new LambdaQueryWrapper<FinanceAccountEntity>()
                        .eq(FinanceAccountEntity::getUserId,CurrentUser.id()))
                .stream().collect(Collectors.toMap(FinanceAccountEntity::getId,FinanceAccountEntity::getName));
        return financeTransactionMapper.selectList(buildFilterQuery(filter)
                        .orderByDesc(FinanceTransactionEntity::getCreatedAt))
                .stream()
                .map(entity -> {
                    FinanceTransactionItem item=entity.toItem();
                    String currentName=names.get(entity.getAccountId());
                    return currentName==null ? item : new FinanceTransactionItem(item.id(),item.type(),
                            item.amount(),item.category(),currentName,item.merchant(),item.note(),
                            item.transactionDate(),item.createdAt());
                })
                .toList();
    }

    @Override
    @Transactional
    public FinanceTransactionItem createTransaction(CreateFinanceTransactionRequest request) {
        LocalDateTime now = LocalDateTime.now();
        FinanceTransactionEntity entity = new FinanceTransactionEntity();
        entity.setUserId(CurrentUser.id());
        entity.setType(request.type());
        entity.setAmount(request.amount());
        entity.setCategory(request.category());
        FinanceAccountEntity account=resolveAccount(request.account());
        entity.setAccount(account.getName());
        entity.setAccountId(account.getId());
        entity.setMerchant(request.merchant() == null ? "" : request.merchant());
        entity.setNote(request.note() == null ? "" : request.note());
        entity.setTransactionDate(request.transactionDate() == null ? LocalDate.now() : request.transactionDate());
        entity.setCreatedAt(now);
        entity.setUpdatedAt(now);
        entity.setDeleted(0);
        financeTransactionMapper.insert(entity);
        return entity.toItem();
    }

    @Override
    @Transactional
    public FinanceTransactionItem updateTransaction(long id, CreateFinanceTransactionRequest request) {
        FinanceTransactionEntity entity = findById(id);
        LocalDateTime now = LocalDateTime.now();
        entity.setType(request.type());
        entity.setAmount(request.amount());
        entity.setCategory(request.category());
        FinanceAccountEntity account=resolveAccount(request.account());
        entity.setAccount(account.getName());
        entity.setAccountId(account.getId());
        entity.setMerchant(request.merchant() == null ? "" : request.merchant());
        entity.setNote(request.note() == null ? "" : request.note());
        entity.setTransactionDate(request.transactionDate() == null ? LocalDate.now() : request.transactionDate());
        entity.setUpdatedAt(now);
        financeTransactionMapper.updateById(entity);
        return entity.toItem();
    }

    @Override
    public void deleteTransaction(long id) {
        findById(id);
        financeTransactionMapper.deleteById(id);
    }

    @Override
    public FinanceMonthlySummary monthlySummary(FinanceTransactionFilter filter) {
        YearMonth current = filter == null || filter.month() == null ? YearMonth.now() : filter.month();
        List<FinanceTransactionEntity> rows = financeTransactionMapper.selectList(
                new LambdaQueryWrapper<FinanceTransactionEntity>()
                        .eq(FinanceTransactionEntity::getUserId, CurrentUser.id())
                        .ge(FinanceTransactionEntity::getTransactionDate, current.atDay(1))
                        .le(FinanceTransactionEntity::getTransactionDate, current.atEndOfMonth()));

        BigDecimal income = BigDecimal.ZERO;
        BigDecimal expense = BigDecimal.ZERO;

        for (FinanceTransactionEntity row : rows) {
            if ("income".equals(row.getType())) {
                income = income.add(row.getAmount());
            } else {
                expense = expense.add(row.getAmount());
            }
        }

        return new FinanceMonthlySummary(income, expense, income.subtract(expense));
    }

    @Override
    public List<FinanceCategorySummary> monthlyCategorySummary(FinanceTransactionFilter filter) {
        List<FinanceTransactionItem> expenseItems = listTransactions(filter).stream()
                .filter(transaction -> "expense".equals(transaction.type()))
                .toList();
        BigDecimal total = expenseItems.stream()
                .map(FinanceTransactionItem::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        if (total.compareTo(BigDecimal.ZERO) == 0) {
            return List.of();
        }
        Map<String, BigDecimal> amountByCategory = expenseItems.stream()
                .collect(Collectors.groupingBy(
                        FinanceTransactionItem::category,
                        Collectors.reducing(BigDecimal.ZERO, FinanceTransactionItem::amount, BigDecimal::add)));
        return amountByCategory.entrySet().stream()
                .map(entry -> new FinanceCategorySummary(
                        entry.getKey(),
                        entry.getValue(),
                        entry.getValue().divide(total, 4, java.math.RoundingMode.HALF_UP)))
                .sorted(Comparator.comparing(FinanceCategorySummary::amount).reversed())
                .toList();
    }

    @Override
    public List<FinanceAccountSummary> monthlyAccountSummary(FinanceTransactionFilter filter) {
        return listTransactions(filter).stream()
                .collect(Collectors.groupingBy(FinanceTransactionItem::account))
                .entrySet()
                .stream()
                .map(entry -> toAccountSummary(entry.getKey(), entry.getValue()))
                .sorted(Comparator.comparing(FinanceAccountSummary::balance).reversed()
                        .thenComparing(FinanceAccountSummary::account))
                .toList();
    }

    private FinanceAccountSummary toAccountSummary(String account, List<FinanceTransactionItem> items) {
        BigDecimal income = items.stream()
                .filter(transaction -> "income".equals(transaction.type()))
                .map(FinanceTransactionItem::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        BigDecimal expense = items.stream()
                .filter(transaction -> "expense".equals(transaction.type()))
                .map(FinanceTransactionItem::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        return new FinanceAccountSummary(account, income, expense, income.subtract(expense));
    }

    private LambdaQueryWrapper<FinanceTransactionEntity> buildFilterQuery(FinanceTransactionFilter filter) {
        FinanceTransactionFilter effectiveFilter = filter == null ? new FinanceTransactionFilter(null, null, null) : filter;
        LambdaQueryWrapper<FinanceTransactionEntity> query = new LambdaQueryWrapper<FinanceTransactionEntity>()
                .eq(FinanceTransactionEntity::getUserId, CurrentUser.id());
        if (effectiveFilter.month() != null) {
            query.ge(FinanceTransactionEntity::getTransactionDate, effectiveFilter.month().atDay(1))
                    .le(FinanceTransactionEntity::getTransactionDate, effectiveFilter.month().atEndOfMonth());
        }
        if (effectiveFilter.type() != null && !effectiveFilter.type().isBlank()) {
            query.eq(FinanceTransactionEntity::getType, effectiveFilter.type());
        }
        if (effectiveFilter.category() != null && !effectiveFilter.category().isBlank()) {
            query.eq(FinanceTransactionEntity::getCategory, effectiveFilter.category());
        }
        return query;
    }

    private FinanceTransactionEntity findById(long id) {
        FinanceTransactionEntity entity = financeTransactionMapper.selectById(id);
        if (entity == null || !java.util.Objects.equals(entity.getUserId(), CurrentUser.id())) {
            throw new ResourceNotFoundException("Finance transaction not found: " + id);
        }
        return entity;
    }
}
