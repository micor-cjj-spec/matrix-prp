package com.matrix.prp.finance.api;

import com.matrix.prp.common.api.ApiResponse;
import com.matrix.prp.finance.model.CreateFinanceAccountRequest;
import com.matrix.prp.finance.model.CreateFinanceCategoryRequest;
import com.matrix.prp.finance.model.CreateFinanceTransactionRequest;
import com.matrix.prp.finance.model.FinanceAccountItem;
import com.matrix.prp.finance.model.FinanceAccountSummary;
import com.matrix.prp.finance.model.FinanceCategoryItem;
import com.matrix.prp.finance.model.FinanceCategorySummary;
import com.matrix.prp.finance.model.FinanceMonthlySummary;
import com.matrix.prp.finance.model.FinanceTransactionFilter;
import com.matrix.prp.finance.model.FinanceTransactionItem;
import com.matrix.prp.finance.service.FinanceService;
import jakarta.validation.Valid;
import java.time.YearMonth;
import java.util.List;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/finance")
public class FinanceController {

    private final FinanceService financeService;

    public FinanceController(FinanceService financeService) {
        this.financeService = financeService;
    }

    @GetMapping("/transactions")
    public ApiResponse<List<FinanceTransactionItem>> listTransactions(
            @RequestParam(required = false) @DateTimeFormat(pattern = "yyyy-MM") YearMonth month,
            @RequestParam(required = false) String type,
            @RequestParam(required = false) String category) {
        return ApiResponse.success(financeService.listTransactions(new FinanceTransactionFilter(month, type, category)));
    }

    @PostMapping("/transactions")
    public ApiResponse<FinanceTransactionItem> createTransaction(
            @Valid @RequestBody CreateFinanceTransactionRequest request) {
        return ApiResponse.success(financeService.createTransaction(request));
    }

    @PutMapping("/transactions/{id}")
    public ApiResponse<FinanceTransactionItem> updateTransaction(
            @PathVariable long id,
            @Valid @RequestBody CreateFinanceTransactionRequest request) {
        return ApiResponse.success(financeService.updateTransaction(id, request));
    }

    @DeleteMapping("/transactions/{id}")
    public ApiResponse<Void> deleteTransaction(@PathVariable long id) {
        financeService.deleteTransaction(id);
        return ApiResponse.success();
    }

    @GetMapping("/summary/monthly")
    public ApiResponse<FinanceMonthlySummary> monthlySummary(
            @RequestParam(required = false) @DateTimeFormat(pattern = "yyyy-MM") YearMonth month) {
        return ApiResponse.success(financeService.monthlySummary(new FinanceTransactionFilter(month, null, null)));
    }

    @GetMapping("/summary/monthly/categories")
    public ApiResponse<List<FinanceCategorySummary>> monthlyCategorySummary(
            @RequestParam(required = false) @DateTimeFormat(pattern = "yyyy-MM") YearMonth month) {
        return ApiResponse.success(financeService.monthlyCategorySummary(new FinanceTransactionFilter(month, "expense", null)));
    }

    @GetMapping("/summary/monthly/accounts")
    public ApiResponse<List<FinanceAccountSummary>> monthlyAccountSummary(
            @RequestParam(required = false) @DateTimeFormat(pattern = "yyyy-MM") YearMonth month) {
        return ApiResponse.success(financeService.monthlyAccountSummary(new FinanceTransactionFilter(month, null, null)));
    }

    @GetMapping("/accounts")
    public ApiResponse<List<FinanceAccountItem>> listAccounts() {
        return ApiResponse.success(financeService.listAccounts());
    }

    @PostMapping("/accounts")
    public ApiResponse<FinanceAccountItem> createAccount(@Valid @RequestBody CreateFinanceAccountRequest request) {
        return ApiResponse.success(financeService.createAccount(request));
    }

    @PutMapping("/accounts/{id}")
    public ApiResponse<FinanceAccountItem> updateAccount(
            @PathVariable long id,
            @Valid @RequestBody CreateFinanceAccountRequest request) {
        return ApiResponse.success(financeService.updateAccount(id, request));
    }

    @DeleteMapping("/accounts/{id}")
    public ApiResponse<Void> deleteAccount(@PathVariable long id) {
        financeService.deleteAccount(id);
        return ApiResponse.success();
    }

    @GetMapping("/categories")
    public ApiResponse<List<FinanceCategoryItem>> listCategories(@RequestParam(required = false) String type) {
        return ApiResponse.success(financeService.listCategories(type));
    }

    @PostMapping("/categories")
    public ApiResponse<FinanceCategoryItem> createCategory(@Valid @RequestBody CreateFinanceCategoryRequest request) {
        return ApiResponse.success(financeService.createCategory(request));
    }

    @PutMapping("/categories/{id}")
    public ApiResponse<FinanceCategoryItem> updateCategory(
            @PathVariable long id,
            @Valid @RequestBody CreateFinanceCategoryRequest request) {
        return ApiResponse.success(financeService.updateCategory(id, request));
    }

    @DeleteMapping("/categories/{id}")
    public ApiResponse<Void> deleteCategory(@PathVariable long id) {
        financeService.deleteCategory(id);
        return ApiResponse.success();
    }
}
