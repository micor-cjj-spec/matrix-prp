package com.matrix.prp.finance.model;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.OffsetDateTime;

public record FinanceTransactionItem(
        long id,
        String type,
        BigDecimal amount,
        String category,
        String account,
        String merchant,
        String note,
        LocalDate transactionDate,
        OffsetDateTime createdAt) {
}
