package com.matrix.prp.finance.model;

import java.time.YearMonth;

public record FinanceTransactionFilter(
        YearMonth month,
        String type,
        String category) {
}
