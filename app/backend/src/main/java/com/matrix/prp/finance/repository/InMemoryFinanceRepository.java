package com.matrix.prp.finance.repository;

import com.matrix.prp.common.api.ResourceNotFoundException;
import com.matrix.prp.finance.model.CreateFinanceTransactionRequest;
import com.matrix.prp.finance.model.FinanceAccountSummary;
import com.matrix.prp.finance.model.FinanceCategorySummary;
import com.matrix.prp.finance.model.FinanceMonthlySummary;
import com.matrix.prp.finance.model.FinanceTransactionFilter;
import com.matrix.prp.finance.model.FinanceTransactionItem;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.YearMonth;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicLong;
import java.util.stream.Collectors;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;

@Repository
@Profile("test")
public class InMemoryFinanceRepository implements FinanceRepository {

    private final AtomicLong idGenerator = new AtomicLong(3000);
    private final CopyOnWriteArrayList<FinanceTransactionItem> transactions = new CopyOnWriteArrayList<>();

    @Override
    public List<FinanceTransactionItem> listTransactions() {
        return listTransactions(new FinanceTransactionFilter(null, null, null));
    }

    @Override
    public List<FinanceTransactionItem> listTransactions(FinanceTransactionFilter filter) {
        FinanceTransactionFilter effectiveFilter = filter == null ? new FinanceTransactionFilter(null, null, null) : filter;
        return transactions.stream()
                .filter(transaction -> effectiveFilter.month() == null
                        || YearMonth.from(transaction.transactionDate()).equals(effectiveFilter.month()))
                .filter(transaction -> effectiveFilter.type() == null || effectiveFilter.type().isBlank()
                        || effectiveFilter.type().equals(transaction.type()))
                .filter(transaction -> effectiveFilter.category() == null || effectiveFilter.category().isBlank()
                        || effectiveFilter.category().equals(transaction.category()))
                .sorted(Comparator.comparing(FinanceTransactionItem::createdAt).reversed())
                .toList();
    }

    @Override
    public FinanceTransactionItem createTransaction(CreateFinanceTransactionRequest request) {
        FinanceTransactionItem transaction = new FinanceTransactionItem(
                idGenerator.incrementAndGet(),
                request.type(),
                request.amount(),
                request.category(),
                request.account() == null ? "default" : request.account(),
                request.merchant() == null ? "" : request.merchant(),
                request.note() == null ? "" : request.note(),
                request.transactionDate() == null ? LocalDate.now() : request.transactionDate(),
                OffsetDateTime.now());
        transactions.add(transaction);
        return transaction;
    }

    @Override
    public FinanceTransactionItem updateTransaction(long id, CreateFinanceTransactionRequest request) {
        FinanceTransactionItem existing = findById(id);
        FinanceTransactionItem updated = new FinanceTransactionItem(
                existing.id(),
                request.type(),
                request.amount(),
                request.category(),
                request.account() == null ? "default" : request.account(),
                request.merchant() == null ? "" : request.merchant(),
                request.note() == null ? "" : request.note(),
                request.transactionDate() == null ? LocalDate.now() : request.transactionDate(),
                existing.createdAt());
        transactions.remove(existing);
        transactions.add(updated);
        return updated;
    }

    @Override
    public void deleteTransaction(long id) {
        boolean removed = transactions.removeIf(transaction -> transaction.id() == id);
        if (!removed) {
            throw new ResourceNotFoundException("Finance transaction not found: " + id);
        }
    }

    @Override
    public FinanceMonthlySummary monthlySummary(FinanceTransactionFilter filter) {
        YearMonth current = filter == null || filter.month() == null ? YearMonth.now() : filter.month();
        BigDecimal income = BigDecimal.ZERO;
        BigDecimal expense = BigDecimal.ZERO;

        for (FinanceTransactionItem transaction : transactions) {
            if (!YearMonth.from(transaction.transactionDate()).equals(current)) {
                continue;
            }
            if ("income".equals(transaction.type())) {
                income = income.add(transaction.amount());
            } else {
                expense = expense.add(transaction.amount());
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

    private FinanceTransactionItem findById(long id) {
        return transactions.stream()
                .filter(transaction -> transaction.id() == id)
                .findFirst()
                .orElseThrow(() -> new ResourceNotFoundException("Finance transaction not found: " + id));
    }
}
