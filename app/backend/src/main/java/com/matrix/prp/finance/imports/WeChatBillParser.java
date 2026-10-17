package com.matrix.prp.finance.imports;

import java.io.ByteArrayInputStream;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.CellType;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.ss.usermodel.DateUtil;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

/** Parse WeChat's personal exported XLSX. No user data is ever sent to AI providers. */
@Component
public class WeChatBillParser {
    private static final String[] HEADERS = {"交易时间","交易类型","交易对方","商品","收/支",
        "金额(元)","支付方式","当前状态","交易单号","商户单号","备注"};
    private static final int MAX_ROWS = 20000;
    private final DataFormatter display = new DataFormatter(Locale.CHINA);

    public record Bill(String sourceAccount, List<BillRow> rows) {}
    public record BillRow(int sourceLine, LocalDateTime transactionAt, String transactionType,
                          String counterparty, String description, String direction, BigDecimal amount,
                          String paymentMethod, String originalStatus, String sourceTransactionId,
                          String merchantTransactionId, String note, String reviewState) {}

    public Bill parse(byte[] bytes) {
        try (XSSFWorkbook workbook = new XSSFWorkbook(new ByteArrayInputStream(bytes))) {
            if (workbook.getNumberOfSheets() != 1) throw invalid("Expected one sheet");
            Sheet sheet = workbook.getSheetAt(0);
            if (sheet.getLastRowNum() > MAX_ROWS + 50) throw invalid("Bill exceeds 20000 rows");
            String sourceAccount = "微信账号";
            for (int i = 0; i < Math.min(12, sheet.getLastRowNum() + 1); i++) {
                Row r = sheet.getRow(i);
                String s = read(r, 0);
                if (s.startsWith("微信昵称：")) {
                    String nickname = s.substring("微信昵称：".length()).replace("［","[")
                        .replace("］","]").replace("[","").replace("]","").trim();
                    if (!nickname.isBlank()) sourceAccount = nickname;
                }
            }
            int header = -1;
            for (int i = 0; i < Math.min(50, sheet.getLastRowNum() + 1); i++) {
                Row r = sheet.getRow(i);
                if (r == null || !HEADERS[0].equals(read(r,0))) continue;
                boolean matching = true;
                for (int col = 0; col < HEADERS.length; col++) {
                    if (!HEADERS[col].equals(read(r,col))) { matching = false; break; }
                }
                if (matching) { header = i; break; }
            }
            if (header < 0) throw invalid("Unrecognized WeChat bill header");
            List<BillRow> rows = new ArrayList<>();
            Set<String> ids = new HashSet<>();
            for (int i = header + 1; i <= sheet.getLastRowNum(); i++) {
                Row row = sheet.getRow(i);
                if (row == null || read(row, 0).isBlank()) continue;
                String sourceId = read(row,8);
                String type = read(row,1);
                String direction = read(row,4);
                String status = read(row,7);
                BigDecimal amount = parseAmount(read(row,5),i+1);
                LocalDateTime at = parseDate(row.getCell(0, Row.MissingCellPolicy.RETURN_BLANK_AS_NULL),i+1);
                boolean refund = type.contains("退款") || status.contains("退款") || status.contains("退还");
                boolean ordinaryExpense = "商户消费".equals(type) && "支出".equals(direction)
                    && "支付成功".equals(status);
                // A refund, red packet, person-to-person transfer or uncertain bank flow must be reviewed.
                String review = ordinaryExpense && !refund && !sourceId.isBlank() && ids.add(sourceId)
                    ? "READY" : "REVIEW";
                rows.add(new BillRow(i+1,at,type,read(row,2),read(row,3),direction,amount,
                    read(row,6),status,sourceId,read(row,9),read(row,10),review));
                if (rows.size() > MAX_ROWS) throw invalid("Bill exceeds 20000 rows");
            }
            if (rows.isEmpty()) throw invalid("No transaction rows found");
            return new Bill(sourceAccount,List.copyOf(rows));
        } catch (ResponseStatusException ex) {
            throw ex;
        } catch (Exception ex) {
            throw invalid("Invalid or unsupported WeChat XLSX");
        }
    }

    private BigDecimal parseAmount(String raw,int line) {
        try {
            String cleaned = raw.replace("¥","").replace("￥","").replace(",","").trim();
            BigDecimal result = new BigDecimal(cleaned).setScale(2);
            if (result.signum() <= 0) throw new NumberFormatException();
            return result;
        } catch (Exception e) {
            throw invalid("Invalid amount at row " + line);
        }
    }

    private LocalDateTime parseDate(Cell cell,int line) {
        try {
            if (cell != null && cell.getCellType() == CellType.NUMERIC) {
                return DateUtil.getLocalDateTime(cell.getNumericCellValue());
            }
            String text = cell == null ? "" : display.formatCellValue(cell).trim();
            return LocalDateTime.parse(text.replace('/','-'),
                DateTimeFormatter.ofPattern("yyyy-M-d H:mm:ss"));
        } catch (Exception e) {
            throw invalid("Invalid date at row " + line);
        }
    }

    private String read(Row row,int index) {
        if (row == null) return "";
        Cell cell=row.getCell(index,Row.MissingCellPolicy.RETURN_BLANK_AS_NULL);
        if (cell == null) return "";
        // 16+ digit payment IDs exported as numeric have already lost precision.
        if ((index == 8 || index == 9) && cell.getCellType() == CellType.NUMERIC
                && cell.getNumericCellValue() >= 1e15) throw invalid("Unsafe numeric transaction ID");
        return display.formatCellValue(cell).replace("\uFEFF","").trim();
    }

    private ResponseStatusException invalid(String detail) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST,detail);
    }
}
