package com.matrix.prp.finance.model;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;

public record CreateFinanceAccountRequest(
        @NotBlank String name,
        String type,
        String currency,
        @NotNull @DecimalMin(value = "0.00") BigDecimal openingBalance,
        String note) {
}
