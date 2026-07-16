package com.matrix.prp.finance.model;

import java.math.BigDecimal;
import java.time.OffsetDateTime;

public record FinanceAccountItem(
        Long id,
        String name,
        String type,
        String currency,
        BigDecimal openingBalance,
        String note,
        OffsetDateTime createdAt) {
}
