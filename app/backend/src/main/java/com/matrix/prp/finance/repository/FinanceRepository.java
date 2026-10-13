package com.matrix.prp.finance.repository;

import com.matrix.prp.finance.model.CreateFinanceTransactionRequest;
import com.matrix.prp.finance.model.FinanceAccountSummary;
import com.matrix.prp.finance.model.FinanceCategorySummary;
import com.matrix.prp.finance.model.FinanceMonthlySummary;
import com.matrix.prp.finance.model.FinanceTransactionFilter;
import com.matrix.prp.finance.model.FinanceTransactionItem;
import java.util.List;

public interface FinanceRepository {

    List<FinanceTransactionItem> listTransactions();

    List<FinanceTransactionItem> listTransactions(FinanceTransactionFilter filter);

    /** Safe generic fallback for in-memory fixtures; MyBatis applies the limit in SQL. */
    default List<FinanceTransactionItem> listTransactionsLimited(FinanceTransactionFilter filter, int limit) {
        if (limit < 1 || limit > 100) throw new IllegalArgumentException("Limit out of range");
        return listTransactions(filter).stream().limit(limit).toList();
    }

    FinanceTransactionItem createTransaction(CreateFinanceTransactionRequest request);

    FinanceTransactionItem updateTransaction(long id, CreateFinanceTransactionRequest request);

    void deleteTransaction(long id);

    FinanceMonthlySummary monthlySummary(FinanceTransactionFilter filter);

    List<FinanceCategorySummary> monthlyCategorySummary(FinanceTransactionFilter filter);

    List<FinanceAccountSummary> monthlyAccountSummary(FinanceTransactionFilter filter);
}
