package com.matrix.prp.finance.model;

import java.math.BigDecimal;

public record FinanceMonthlySummary(
        BigDecimal income,
        BigDecimal expense,
        BigDecimal balance) {
}
