package com.matrix.prp;

import static org.assertj.core.api.Assertions.*;
import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.finance.imports.FinanceImportService;
import com.matrix.prp.finance.mapper.FinanceAccountMapper;
import com.matrix.prp.finance.entity.FinanceAccountEntity;
import java.io.ByteArrayOutputStream;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.web.server.ResponseStatusException;

@SpringBootTest
@ActiveProfiles("video-integration")
class FinanceImportDatabaseIT {
    @Autowired FinanceImportService imports;
    @Autowired FinanceAccountMapper accounts;

    private void owner(long id) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(new UserProfile(id,"fixture","Test Owner"),null,List.of()));
    }

    private byte[] sample(String id) throws Exception {
        try (var excel=new XSSFWorkbook(); var stream=new ByteArrayOutputStream()) {
            var sheet=excel.createSheet();
            sheet.createRow(1).createCell(0).setCellValue("微信昵称：[Fixture]");
            var header=sheet.createRow(17);
            String[] h={"交易时间","交易类型","交易对方","商品","收/支","金额(元)",
                "支付方式","当前状态","交易单号","商户单号","备注"};
            for(int i=0;i<h.length;i++)header.createCell(i).setCellValue(h[i]);
            String[][] rows={
                {"2026-10-14 00:24:20","商户消费","Fixture Shop","meal","支出","36.70","零钱","支付成功","45"+id,"a","/"},
                {"2026-10-14 00:25:20","商户消费","Fixture Shop","refund","支出","9.00","零钱","已全额退款","46"+id,"b","/"},
                {"2026-10-14 00:26:20","转账","Fixture Contact","transfer","支出","100.00","零钱","对方已收钱","47"+id,"c","/"}
            };
            for(int n=0;n<rows.length;n++) {
                var row=sheet.createRow(18+n);
                for(int c=0;c<h.length;c++)row.createCell(c).setCellValue(rows[n][c]);
            }
            excel.write(stream);
            return stream.toByteArray();
        }
    }

    @Test void importsSafeExpenseOnlyAndRefusesCrossUserOrRepeat() throws Exception {
        long first=8023501L,second=8023502L;
        String id=UUID.randomUUID().toString().replace("-","");
        byte[] bytes=sample(id);
        var upload=new MockMultipartFile("file","wechat.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",bytes);
        owner(first);
        var account=new FinanceAccountEntity();
        account.setUserId(first);account.setName("import-test-"+id);account.setType("cash");
        account.setCurrency("CNY");account.setOpeningBalance(BigDecimal.valueOf(100));
        account.setCreatedAt(LocalDateTime.now());account.setUpdatedAt(account.getCreatedAt());
        account.setDeleted(0);account.setNote("test");
        accounts.insert(account);
        var preview=imports.preview(upload,null);
        assertThat(preview.ready()).isEqualTo(1);
        assertThat(preview.review()).isEqualTo(2);
        assertThat(preview.posted()).isZero();
        assertThat(imports.preview(upload,null).id()).isEqualTo(preview.id());
        var command=new FinanceImportService.CommitRequest(Map.of("零钱",account.getId()));
        var done=imports.commit(preview.id(),command);
        assertThat(done.ready()).isZero();
        assertThat(done.review()).isEqualTo(2);
        assertThat(done.posted()).isEqualTo(1);
        assertThat(imports.commit(preview.id(),command).posted()).isEqualTo(1);
        assertThatThrownBy(()->imports.preview(upload,"another-source"))
            .isInstanceOf(ResponseStatusException.class);
        owner(second);
        assertThatThrownBy(()->imports.detail(preview.id()))
            .isInstanceOf(ResponseStatusException.class);
        assertThatThrownBy(()->imports.commit(preview.id(),command))
            .isInstanceOf(ResponseStatusException.class);
        SecurityContextHolder.clearContext();
    }
    @Test void keepsUnmappedExpensesPendingUntilMapped() throws Exception {
        long user = 8023511L;
        String fixtureId = UUID.randomUUID().toString().replace("-", "");
        var upload = new MockMultipartFile("file", "wechat.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", sample(fixtureId));
        try {
            owner(user);
            var preview = imports.preview(upload, null);
            assertThat(preview.ready()).isEqualTo(1);
            var unmapped = imports.commit(preview.id(), new FinanceImportService.CommitRequest(Map.of()));
            assertThat(unmapped.status()).isEqualTo("PARTIAL");
            assertThat(unmapped.ready()).isEqualTo(1);
            assertThat(unmapped.posted()).isZero();
            assertThat(unmapped.review()).isEqualTo(2);

            var account = new FinanceAccountEntity();
            account.setUserId(user);
            account.setName("explicit-account-" + fixtureId);
            account.setType("cash");
            account.setCurrency("CNY");
            account.setOpeningBalance(BigDecimal.ZERO);
            account.setCreatedAt(LocalDateTime.now());
            account.setUpdatedAt(account.getCreatedAt());
            account.setDeleted(0);
            account.setNote("test");
            accounts.insert(account);

            var mapping = new FinanceImportService.CommitRequest(Map.of("零钱", account.getId()));
            var posted = imports.commit(preview.id(), mapping);
            assertThat(posted.status()).isEqualTo("DONE");
            assertThat(posted.ready()).isZero();
            assertThat(posted.posted()).isEqualTo(1);
            assertThat(posted.review()).isEqualTo(2);
            // A second click must not create another finance ledger entry.
            assertThat(imports.commit(preview.id(), mapping).posted()).isEqualTo(1);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    @Test void refusesMappingToAnotherUsersFinanceAccountWithoutPosting() throws Exception {
        long user = 8023512L, otherUser = 8023513L;
        String fixtureId = UUID.randomUUID().toString().replace("-", "");
        var upload = new MockMultipartFile("file", "wechat.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", sample(fixtureId));
        try {
            owner(otherUser);
            var foreignAccount = new FinanceAccountEntity();
            foreignAccount.setUserId(otherUser);
            foreignAccount.setName("other-tenant-" + fixtureId);
            foreignAccount.setType("cash");
            foreignAccount.setCurrency("CNY");
            foreignAccount.setOpeningBalance(BigDecimal.ZERO);
            foreignAccount.setCreatedAt(LocalDateTime.now());
            foreignAccount.setUpdatedAt(foreignAccount.getCreatedAt());
            foreignAccount.setDeleted(0);
            foreignAccount.setNote("test");
            accounts.insert(foreignAccount);

            owner(user);
            var preview = imports.preview(upload, null);
            var mapping = new FinanceImportService.CommitRequest(Map.of("零钱", foreignAccount.getId()));
            assertThatThrownBy(() -> imports.commit(preview.id(), mapping))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("owned CNY account");
            var unchanged = imports.detail(preview.id());
            assertThat(unchanged.posted()).isZero();
            assertThat(unchanged.ready()).isEqualTo(1);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

}
