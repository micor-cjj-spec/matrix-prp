package com.matrix.prp.finance.api;

import com.matrix.prp.common.api.ApiResponse;
import com.matrix.prp.finance.model.CreateFinanceTransferRequest;
import com.matrix.prp.finance.model.FinanceAccountBalance;
import com.matrix.prp.finance.model.FinanceTransferItem;
import com.matrix.prp.finance.service.FinanceLedgerService;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.*;

@RestController
@Profile("!test")
@RequestMapping("/api/finance")
public class FinanceLedgerController {
    private final FinanceLedgerService ledger;
    public FinanceLedgerController(FinanceLedgerService ledger) { this.ledger=ledger; }
    @GetMapping("/accounts/balances")
    public ApiResponse<List<FinanceAccountBalance>> balances() {
        return ApiResponse.success(ledger.accountBalances());
    }
    @GetMapping("/transfers")
    public ApiResponse<List<FinanceTransferItem>> transfers() {
        return ApiResponse.success(ledger.listTransfers());
    }
    @PostMapping("/transfers")
    public ApiResponse<FinanceTransferItem> create(@Valid @RequestBody CreateFinanceTransferRequest request) {
        return ApiResponse.success(ledger.createTransfer(request));
    }
    @DeleteMapping("/transfers/{id}")
    public ApiResponse<Void> remove(@PathVariable long id) {
        ledger.deleteTransfer(id);
        return ApiResponse.success();
    }
}
