package com.matrix.prp.finance.imports;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import java.math.BigDecimal;
import java.sql.PreparedStatement;
import java.sql.Statement;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.BatchPreparedStatementSetter;
import org.springframework.jdbc.core.JdbcTemplate;

class FinanceImportStagingRepositoryTests {
    private FinanceImportStagingRepository.StagedRow item(int line) {
        var row = new WeChatBillParser.BillRow(line,
            LocalDateTime.of(2026, 10, 14, 1, 2, 3),
            "商户消费", "test shop", "synthetic lunch", "支出", new BigDecimal("36.70"),
            "零钱", "支付成功", "id-" + line, "merchant", "memo", "READY");
        return new FinanceImportStagingRepository.StagedRow(row,"READY");
    }

    @Test void twentyThousandRowsUseEightyBoundedJdbcBatchCalls() {
        JdbcTemplate jdbc=mock(JdbcTemplate.class);
        AtomicInteger calls=new AtomicInteger();
        when(jdbc.batchUpdate(anyString(), any(BatchPreparedStatementSetter.class))).thenAnswer(inv -> {
            BatchPreparedStatementSetter setter=inv.getArgument(1);
            assertThat(setter.getBatchSize()).isBetween(1,250);
            assertThat(inv.<String>getArgument(0)).contains("INSERT INTO prp_finance_import_rows");
            calls.incrementAndGet();
            int[] results=new int[setter.getBatchSize()];
            java.util.Arrays.fill(results, Statement.SUCCESS_NO_INFO);
            return results;
        });
        var rows=new ArrayList<FinanceImportStagingRepository.StagedRow>(20000);
        for(int i=1;i<=20000;i++)rows.add(item(i));
        new FinanceImportStagingRepository(jdbc).insertRows(456L,123L,rows);
        assertThat(calls.get()).isEqualTo(80);
    }

    @Test void partialLastBatchRetainsOrderBoundParamsAndSourceStatus() throws Exception {
        JdbcTemplate jdbc=mock(JdbcTemplate.class);
        List<BatchPreparedStatementSetter> setters=new ArrayList<>();
        when(jdbc.batchUpdate(anyString(), any(BatchPreparedStatementSetter.class))).thenAnswer(inv -> {
            BatchPreparedStatementSetter setter=inv.getArgument(1);
            setters.add(setter);
            int[] result=new int[setter.getBatchSize()];
            java.util.Arrays.fill(result,1);
            return result;
        });
        List<FinanceImportStagingRepository.StagedRow> rows=new ArrayList<>();
        for(int i=1;i<=501;i++)rows.add(item(i));
        rows.set(500,new FinanceImportStagingRepository.StagedRow(item(501).source(),"REVIEW"));
        new FinanceImportStagingRepository(jdbc).insertRows(456L,123L,rows);
        assertThat(setters.stream().map(BatchPreparedStatementSetter::getBatchSize).toList())
            .containsExactly(250,250,1);
        PreparedStatement ps=mock(PreparedStatement.class);
        setters.get(0).setValues(ps,0);
        verify(ps).setLong(1,456L);
        verify(ps).setLong(2,123L);
        verify(ps).setInt(3,1);
        verify(ps).setBigDecimal(11,new BigDecimal("36.70"));
        verify(ps).setString(15,"READY");
        reset(ps);
        setters.get(2).setValues(ps,0);
        verify(ps).setInt(3,501);
        verify(ps).setString(4,"id-501");
        verify(ps).setString(15,"REVIEW");
    }

    @Test void failuresAndMissingRowsAreNeverAccepted() {
        JdbcTemplate jdbc=mock(JdbcTemplate.class);
        var writer=new FinanceImportStagingRepository(jdbc);
        writer.insertRows(1L,2L,List.of());
        verifyNoInteractions(jdbc);
        for(int[] invalid : new int[][]{{}, {0}, {Statement.EXECUTE_FAILED}, {2}}) {
            reset(jdbc);
            when(jdbc.batchUpdate(anyString(),any(BatchPreparedStatementSetter.class)))
                .thenReturn(invalid);
            assertThatThrownBy(()->writer.insertRows(1L,2L,List.of(item(1))))
                .isInstanceOf(IllegalStateException.class);
        }
        reset(jdbc);
        when(jdbc.batchUpdate(anyString(),any(BatchPreparedStatementSetter.class)))
            .thenThrow(new org.springframework.dao.DataIntegrityViolationException("synthetic"));
        assertThatThrownBy(()->writer.insertRows(1L,2L,List.of(item(1))))
            .isInstanceOf(org.springframework.dao.DataIntegrityViolationException.class);
    }
}
