package com.matrix.prp.finance.model;

import java.math.BigDecimal;

public record FinanceAccountSummary(
        String account,
        BigDecimal income,
        BigDecimal expense,
        BigDecimal balance) {
}
