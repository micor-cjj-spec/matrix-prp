package com.matrix.prp.finance.imports;

import static org.assertj.core.api.Assertions.*;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.time.LocalDateTime;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;

class WeChatBillParserTests {
    private static final String[] H = {"交易时间","交易类型","交易对方","商品","收/支",
        "金额(元)","支付方式","当前状态","交易单号","商户单号","备注"};
    private byte[] workbook() throws Exception {
        try(var x=new XSSFWorkbook();var out=new ByteArrayOutputStream()){
            var s=x.createSheet("Sheet1");
            s.createRow(1).createCell(0).setCellValue("微信昵称：[TestUser]");
            Row header=s.createRow(17);
            for(int i=0;i<H.length;i++) header.createCell(i).setCellValue(H[i]);
            Row expense=s.createRow(18);
            expense.createCell(0).setCellValue(46309.01689814815);
            expense.createCell(1).setCellValue("商户消费");
            expense.createCell(2).setCellValue("商店");
            expense.createCell(3).setCellValue("午餐");
            expense.createCell(4).setCellValue("支出");
            expense.createCell(5).setCellValue(36.7);
            expense.createCell(6).setCellValue("零钱");
            expense.createCell(7).setCellValue("支付成功");
            expense.createCell(8).setCellValue("4500000443202610148070669425");
            expense.createCell(9).setCellValue("merchant-1");
            Row refunded=s.createRow(19);
            refunded.createCell(0).setCellValue(46309.1);
            refunded.createCell(1).setCellValue("商户消费");
            refunded.createCell(4).setCellValue("支出");
            refunded.createCell(5).setCellValue("¥16.63");
            refunded.createCell(6).setCellValue("零钱");
            refunded.createCell(7).setCellValue("已全额退款");
            refunded.createCell(8).setCellValue("4500000443202610148070669426");
            x.write(out);return out.toByteArray();
        }
    }
    @Test void parsesNumericExcelDatesAndProtectsRefunds() throws Exception {
        var result=new WeChatBillParser().parse(workbook());
        assertThat(result.sourceAccount()).isEqualTo("TestUser");
        assertThat(result.rows()).hasSize(2);
        assertThat(result.rows().get(0).transactionAt()).isEqualTo(LocalDateTime.of(2026,10,14,0,24,20));
        assertThat(result.rows().get(0).amount()).isEqualByComparingTo("36.70");
        assertThat(result.rows().get(0).reviewState()).isEqualTo("READY");
        assertThat(result.rows().get(1).reviewState()).isEqualTo("REVIEW");
    }
    @Test void rejectsGarbage() {
        assertThatThrownBy(()->new WeChatBillParser().parse(new byte[]{1,2,3}))
            .isInstanceOf(ResponseStatusException.class);
    }
    @Test void flagsDuplicateSourceTransactionIdsForReview() throws Exception {
        try (var excel = new XSSFWorkbook(new ByteArrayInputStream(workbook()));
             var output = new ByteArrayOutputStream()) {
            var second = excel.getSheetAt(0).createRow(20);
            String[] fields = {
                "2026-10-14 00:27:20", "商户消费", "重复商店", "晚餐", "支出",
                "12.00", "零钱", "支付成功", "4500000443202610148070669425", "merchant-2", ""
            };
            for (int i = 0; i < fields.length; i++) {
                second.createCell(i).setCellValue(fields[i]);
            }
            excel.write(output);
            var parsed = new WeChatBillParser().parse(output.toByteArray());
            assertThat(parsed.rows()).hasSize(3);
            assertThat(parsed.rows().get(0).reviewState()).isEqualTo("READY");
            assertThat(parsed.rows().get(1).reviewState()).isEqualTo("REVIEW"); // refunded
            assertThat(parsed.rows().get(2).reviewState()).isEqualTo("REVIEW"); // same source ID
        }
    }

}
