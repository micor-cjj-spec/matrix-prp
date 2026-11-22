package com.matrix.prp.finance.imports;

import static org.assertj.core.api.Assertions.*;

import com.matrix.prp.finance.entity.FinanceAccountEntity;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;

class FinanceImportPolicyTests {
    private FinanceAccountEntity account(long id, long owner, String currency, int deleted) {
        FinanceAccountEntity a = new FinanceAccountEntity();
        a.setId(id);
        a.setUserId(owner);
        a.setName("零钱");
        a.setCurrency(currency);
        a.setDeleted(deleted);
        return a;
    }

    @Test
    void resolvesSourceWithSameOverridesAndLimits() {
        assertThat(FinanceImportPolicy.sourceAccountKey(null, "微信账号")).isEqualTo("微信账号");
        assertThat(FinanceImportPolicy.sourceAccountKey(" ", "张三")).isEqualTo("张三");
        assertThat(FinanceImportPolicy.sourceAccountKey("  个人钱包  ", "ignored"))
                .isEqualTo("个人钱包");
        assertThatThrownBy(() -> FinanceImportPolicy.sourceAccountKey("  ", "  "))
                .isInstanceOf(ResponseStatusException.class);
        assertThatThrownBy(() -> FinanceImportPolicy.sourceAccountKey(" ", ""))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("Invalid source account key");
        assertThatThrownBy(() -> FinanceImportPolicy.sourceAccountKey("X".repeat(129), "ok"))
                .isInstanceOf(ResponseStatusException.class);
    }

    @Test
    void sanitizesFilenamesWithoutPersistingDirectoriesOrControlCharacters() {
        assertThat(FinanceImportPolicy.safeOriginalFilename("C:\\private\\账单.xlsx"))
                .isEqualTo("账单.xlsx");
        assertThat(FinanceImportPolicy.safeOriginalFilename("../\n2026\t账单.xlsx"))
                .isEqualTo("2026账单.xlsx");
        assertThat(FinanceImportPolicy.safeOriginalFilename("前缀".repeat(150) + ".xlsx"))
                .hasSize(255).endsWith(".xlsx");
    }

    @Test
    void duplicateClassificationRetainsReviewAndAvoidsRedundantLookups() {
        Set<String> seen = new HashSet<>();
        AtomicInteger dbQueries = new AtomicInteger();
        assertThat(FinanceImportPolicy.previewRowStatus("READY", "source-1", seen,
                () -> { dbQueries.incrementAndGet(); return false; })).isEqualTo("READY");
        assertThat(FinanceImportPolicy.previewRowStatus("READY", "source-1", seen,
                () -> { dbQueries.incrementAndGet(); return false; })).isEqualTo("DUPLICATE");
        assertThat(dbQueries.get()).isEqualTo(1);
        assertThat(FinanceImportPolicy.previewRowStatus("REVIEW", "source-2", seen,
                () -> { dbQueries.incrementAndGet(); return false; })).isEqualTo("REVIEW");
        assertThat(FinanceImportPolicy.previewRowStatus("REVIEW", "source-3", seen,
                () -> { dbQueries.incrementAndGet(); return true; })).isEqualTo("DUPLICATE");
        assertThat(FinanceImportPolicy.previewRowStatus("REVIEW", "", seen,
                () -> { throw new AssertionError("Blank transaction ID must not hit DB"); }))
                .isEqualTo("REVIEW");
        assertThat(dbQueries.get()).isEqualTo(3);
    }

    @Test
    void mappingAcceptsOnlyLiveTenantOwnedCnyAccounts() {
        FinanceAccountEntity owned = account(88L, 99L, "CNY", 0);
        assertThat(FinanceImportPolicy.requireOwnedCnyAccount(owned, 99L)).isSameAs(owned);
        for (FinanceAccountEntity disallowed : new FinanceAccountEntity[]{
                null, account(88L, 100L, "CNY", 0),
                account(88L, 99L, "USD", 0),
                account(88L, 99L, "CNY", 1),
                account(88L, 99L, null, 0),
                account(88L, 99L, "CNY", 2)}) {
            assertThatThrownBy(() -> FinanceImportPolicy.requireOwnedCnyAccount(disallowed, 99L))
                    .isInstanceOf(ResponseStatusException.class)
                    .hasMessageContaining("Account must be an owned CNY account");
        }
    }

    @Test
    void postingMapsAllOriginalLedgerFieldsWithoutChangingTenantOrAmount() {
        FinanceAccountEntity account = account(88L, 99L, "CNY", 0);
        LocalDateTime at = LocalDateTime.of(2026, 10, 14, 1, 2, 3);
        LocalDateTime now = LocalDateTime.of(2026, 10, 21, 14, 30);
        var item = FinanceImportPolicy.newPostedExpense(
                99L, account, new BigDecimal("36.70"), "Fixture Shop",
                "测试午餐", at, now);
        assertThat(item.getUserId()).isEqualTo(99L);
        assertThat(item.getAccountId()).isEqualTo(88L);
        assertThat(item.getAccount()).isEqualTo("零钱");
        assertThat(item.getType()).isEqualTo("expense");
        assertThat(item.getAmount()).isEqualByComparingTo("36.70");
        assertThat(item.getCategory()).isEqualTo("待分类");
        assertThat(item.getMerchant()).isEqualTo("Fixture Shop");
        assertThat(item.getNote()).isEqualTo("微信账单导入：测试午餐");
        assertThat(item.getTransactionDate()).isEqualTo(at.toLocalDate());
        assertThat(item.getCreatedAt()).isEqualTo(now);
        assertThat(item.getUpdatedAt()).isEqualTo(now);
        assertThat(item.getDeleted()).isZero();
    }
}
