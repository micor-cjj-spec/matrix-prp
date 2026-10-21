package com.matrix.prp.finance.imports;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.mockito.invocation.Invocation;
import org.springframework.jdbc.core.JdbcTemplate;

class FinanceImportSourceLinkRepositoryTests {
    private WeChatBillParser.BillRow row(int i, String txid) {
        return new WeChatBillParser.BillRow(
            i, LocalDateTime.of(2026, 10, 21, 12, 0),
            "商户消费", "synthetic", "lunch", "支出", new BigDecimal("9.00"),
            "零钱", "支付成功", txid, "merchant-id", "", "READY");
    }

    @Test
    void emptyAndBlankIdsNeverQueryDatabase() {
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        FinanceImportSourceLinkRepository repository = new FinanceImportSourceLinkRepository(jdbc);
        assertThat(repository.findPostedPreviewIds(77, List.of())).isEmpty();
        assertThat(repository.findPostedPreviewIds(77, List.of(row(1,""), row(2," ")))).isEmpty();
        verifyNoInteractions(jdbc);
    }

    @Test
    void previewOfTwentyThousandDistinctRowsUsesEightyBoundedQueries() {
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        FinanceImportSourceLinkRepository repo = new FinanceImportSourceLinkRepository(jdbc);
        List<WeChatBillParser.BillRow> rows = new ArrayList<>();
        for (int i = 0; i < 20000; i++) {
            rows.add(row(i+1, String.format("tx-%05d", i)));
        }
        assertThat(repo.findPostedPreviewIds(88L, rows)).isEmpty();
        List<Invocation> queries = mockingDetails(jdbc).getInvocations().stream()
            .filter(i -> i.getMethod().getName().equals("queryForList")).toList();
        assertThat(queries).hasSize(80);
        int boundIds = 0;
        for (Invocation invocation : queries) {
            Object[] args = invocation.getRawArguments();
            String sql = (String) args[0];
            Object[] binds = (Object[]) args[2];
            assertThat(sql).contains("links.user_id=?", "links.platform='WECHAT'",
                "links.source_transaction_id=submitted.source_id",
                "COLLATE utf8mb4_unicode_ci");
            assertThat(sql).doesNotContain("tx-00000");
            assertThat(binds).hasSize(251);
            assertThat(binds[250]).isEqualTo(88L);
            assertThat(sql.chars().filter(c -> c == '?').count()).isEqualTo(251L);
            boundIds += binds.length - 1;
        }
        assertThat(boundIds).isEqualTo(20000);
    }

    @Test
    void onlyDistinctNonBlankIDsAreBoundAndNeverInterpolated() {
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        FinanceImportSourceLinkRepository repository = new FinanceImportSourceLinkRepository(jdbc);
        String hostile = "' OR 1=1 --";
        repository.findPostedPreviewIds(91L,
            List.of(row(1,hostile),row(2,hostile),row(3,"safe"),row(4,"")));
        Invocation one = mockingDetails(jdbc).getInvocations().iterator().next();
        Object[] args = one.getRawArguments();
        String sql = (String) args[0];
        assertThat(sql).doesNotContain(hostile);
        assertThat((Object[]) args[2]).containsExactly(hostile, "safe", 91L);
    }

    @Test
    void rejectsOutOfBoundBatchesAndRetainsCommitTimeLiveCheck() {
        assertThatThrownBy(() -> FinanceImportSourceLinkRepository.plan(9L,List.of()))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> FinanceImportSourceLinkRepository.plan(
            9L,java.util.Collections.nCopies(251,"id")))
            .isInstanceOf(IllegalArgumentException.class);
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        FinanceImportSourceLinkRepository repository = new FinanceImportSourceLinkRepository(jdbc);
        when(jdbc.queryForObject(anyString(), eq(Integer.class), eq(91L), eq("external")))
            .thenReturn(1);
        assertThat(repository.alreadyPosted(91L,"external")).isTrue();
        verify(jdbc).queryForObject(
            "SELECT COUNT(*) FROM prp_finance_source_links " +
            "WHERE user_id=? AND platform='WECHAT' AND source_transaction_id=?",
            Integer.class,91L,"external");
    }
}
