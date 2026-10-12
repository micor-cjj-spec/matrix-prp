package com.matrix.prp.finance.model;

import java.math.BigDecimal;

public record FinanceAccountBalance(
        long accountId, String account, String currency,
        BigDecimal openingBalance, BigDecimal income, BigDecimal expense,
        BigDecimal transferIn, BigDecimal transferOut, BigDecimal currentBalance) {
}
