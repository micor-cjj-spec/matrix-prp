package com.matrix.prp.finance.service;

import com.matrix.prp.finance.model.CreateFinanceTransactionRequest;
import com.matrix.prp.finance.model.CreateFinanceAccountRequest;
import com.matrix.prp.finance.model.CreateFinanceCategoryRequest;
import com.matrix.prp.finance.model.FinanceAccountItem;
import com.matrix.prp.finance.model.FinanceAccountSummary;
import com.matrix.prp.finance.model.FinanceCategoryItem;
import com.matrix.prp.finance.model.FinanceCategorySummary;
import com.matrix.prp.finance.model.FinanceMonthlySummary;
import com.matrix.prp.finance.model.FinanceTransactionFilter;
import com.matrix.prp.finance.model.FinanceTransactionItem;
import com.matrix.prp.finance.repository.FinanceConfigRepository;
import com.matrix.prp.finance.repository.FinanceRepository;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class FinanceService {

    private final FinanceRepository financeRepository;
    private final FinanceConfigRepository financeConfigRepository;

    public FinanceService(FinanceRepository financeRepository, FinanceConfigRepository financeConfigRepository) {
        this.financeRepository = financeRepository;
        this.financeConfigRepository = financeConfigRepository;
    }

    public List<FinanceTransactionItem> listTransactions() {
        return financeRepository.listTransactions();
    }

    public List<FinanceTransactionItem> listTransactions(FinanceTransactionFilter filter) {
        return financeRepository.listTransactions(filter);
    }

    public List<FinanceTransactionItem> listTransactionsLimited(FinanceTransactionFilter filter, int limit) {
        return financeRepository.listTransactionsLimited(filter, limit);
    }

    public FinanceTransactionItem createTransaction(CreateFinanceTransactionRequest request) {
        return financeRepository.createTransaction(request);
    }

    public FinanceTransactionItem updateTransaction(long id, CreateFinanceTransactionRequest request) {
        return financeRepository.updateTransaction(id, request);
    }

    public void deleteTransaction(long id) {
        financeRepository.deleteTransaction(id);
    }

    public FinanceMonthlySummary monthlySummary() {
        return monthlySummary(new FinanceTransactionFilter(null, null, null));
    }

    public FinanceMonthlySummary monthlySummary(FinanceTransactionFilter filter) {
        return financeRepository.monthlySummary(filter);
    }

    public List<FinanceCategorySummary> monthlyCategorySummary(FinanceTransactionFilter filter) {
        return financeRepository.monthlyCategorySummary(filter);
    }

    public List<FinanceAccountSummary> monthlyAccountSummary(FinanceTransactionFilter filter) {
        return financeRepository.monthlyAccountSummary(filter);
    }

    public List<FinanceAccountItem> listAccounts() {
        return financeConfigRepository.listAccounts();
    }

    public FinanceAccountItem createAccount(CreateFinanceAccountRequest request) {
        return financeConfigRepository.createAccount(request);
    }

    public FinanceAccountItem updateAccount(long id, CreateFinanceAccountRequest request) {
        return financeConfigRepository.updateAccount(id, request);
    }

    public void deleteAccount(long id) {
        financeConfigRepository.deleteAccount(id);
    }

    public List<FinanceCategoryItem> listCategories(String type) {
        return financeConfigRepository.listCategories(type);
    }

    public FinanceCategoryItem createCategory(CreateFinanceCategoryRequest request) {
        return financeConfigRepository.createCategory(request);
    }

    public FinanceCategoryItem updateCategory(long id, CreateFinanceCategoryRequest request) {
        return financeConfigRepository.updateCategory(id, request);
    }

    public void deleteCategory(long id) {
        financeConfigRepository.deleteCategory(id);
    }
}
