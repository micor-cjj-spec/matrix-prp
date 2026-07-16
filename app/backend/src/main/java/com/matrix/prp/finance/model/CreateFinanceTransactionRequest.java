package com.matrix.prp.finance.model;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import java.math.BigDecimal;
import java.time.LocalDate;

public record CreateFinanceTransactionRequest(
        @Pattern(regexp = "income|expense", message = "must be one of: income, expense")
        @NotBlank String type,
        @NotNull @DecimalMin("0.01") BigDecimal amount,
        @NotBlank String category,
        String account,
        String merchant,
        String note,
        LocalDate transactionDate) {
}
