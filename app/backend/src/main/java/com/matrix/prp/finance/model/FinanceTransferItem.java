package com.matrix.prp.finance.model;

import java.math.BigDecimal;
import java.time.LocalDate;

public record FinanceTransferItem(long id, long fromAccountId, String fromAccount,
                                  long toAccountId, String toAccount, BigDecimal amount,
                                  String currency, LocalDate transferDate, String note) {
}
