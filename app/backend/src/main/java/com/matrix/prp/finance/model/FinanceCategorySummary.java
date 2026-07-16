package com.matrix.prp.finance.model;

import java.math.BigDecimal;

public record FinanceCategorySummary(
        String category,
        BigDecimal amount,
        BigDecimal ratio) {
}
