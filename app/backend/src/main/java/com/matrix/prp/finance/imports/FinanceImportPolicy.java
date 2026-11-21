package com.matrix.prp.finance.imports;

import com.matrix.prp.finance.entity.FinanceAccountEntity;
import com.matrix.prp.finance.entity.FinanceTransactionEntity;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.Objects;
import java.util.Set;
import java.util.function.BooleanSupplier;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

/**
 * Business invariants for the WeChat import boundary.
 *
 * This class is deliberately free of SQL, HTTP, transactions and Spring state:
 * the caller retains locks, unique-key protection, tenant-scoped queries and
 * the atomic ledger/source-link write transaction.
 */
final class FinanceImportPolicy {
    static final String READY = "READY";
    static final String REVIEW = "REVIEW";
    static final String DUPLICATE = "DUPLICATE";
    static final String POSTED = "POSTED";

    private FinanceImportPolicy() {}

    static String sourceAccountKey(String override, String detected) {
        String source = override == null || override.isBlank() ? detected : override.trim();
        if (source == null || source.length() > 128 || source.isBlank()) {
            throw bad("Invalid source account key");
        }
        return source;
    }

    static String safeOriginalFilename(String original) {
        String filename = original.replace('\\', '/').replaceAll("^.*/", "")
                .replaceAll("[\\p{Cntrl}]", "").trim();
        if (filename.length() > 255) {
            filename = filename.substring(filename.length() - 255);
        }
        return filename;
    }

    static String previewRowStatus(String parserStatus, String sourceTransactionId,
                                   Set<String> seenInFile, BooleanSupplier alreadyPosted) {
        // Preserve original ordering and short circuit: a duplicate in this
        // same file does not require a database lookup.
        if (!sourceTransactionId.isBlank() &&
                (!seenInFile.add(sourceTransactionId) || alreadyPosted.getAsBoolean())) {
            return DUPLICATE;
        }
        return parserStatus;
    }

    static FinanceAccountEntity requireOwnedCnyAccount(FinanceAccountEntity account, long owner) {
        if (account == null || !Objects.equals(account.getUserId(), owner)
                || !Objects.equals(account.getDeleted(), 0)
                || !"CNY".equals(account.getCurrency())) {
            throw bad("Account must be an owned CNY account");
        }
        return account;
    }

    static FinanceTransactionEntity newPostedExpense(
            long owner, FinanceAccountEntity account, BigDecimal amount,
            String counterparty, String description, LocalDateTime transactionAt,
            LocalDateTime now) {
        FinanceTransactionEntity ledger = new FinanceTransactionEntity();
        ledger.setUserId(owner);
        ledger.setType("expense");
        ledger.setAmount(amount);
        ledger.setCategory("待分类");
        ledger.setAccount(account.getName());
        ledger.setAccountId(account.getId());
        ledger.setMerchant(counterparty);
        ledger.setNote("微信账单导入：" + description);
        ledger.setTransactionDate(transactionAt.toLocalDate());
        ledger.setCreatedAt(now);
        ledger.setUpdatedAt(now);
        ledger.setDeleted(0);
        return ledger;
    }

    private static ResponseStatusException bad(String message) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, message);
    }
}
