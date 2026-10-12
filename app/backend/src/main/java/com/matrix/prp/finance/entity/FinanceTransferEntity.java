package com.matrix.prp.finance.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableLogic;
import com.baomidou.mybatisplus.annotation.TableName;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;

@TableName("prp_finance_transfers")
public class FinanceTransferEntity {
    @TableId(type = IdType.AUTO)
    private Long id;
    private Long userId;
    private Long fromAccountId;
    private Long toAccountId;
    private BigDecimal amount;
    private LocalDate transferDate;
    private String note;
    private String clientRequestId;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
    @TableLogic private Integer deleted;
    public Long getId() { return id; }
    public void setId(Long v) { id=v; }
    public Long getUserId() { return userId; }
    public void setUserId(Long v) { userId=v; }
    public Long getFromAccountId() { return fromAccountId; }
    public void setFromAccountId(Long v) { fromAccountId=v; }
    public Long getToAccountId() { return toAccountId; }
    public void setToAccountId(Long v) { toAccountId=v; }
    public BigDecimal getAmount() { return amount; }
    public void setAmount(BigDecimal v) { amount=v; }
    public LocalDate getTransferDate() { return transferDate; }
    public void setTransferDate(LocalDate v) { transferDate=v; }
    public String getNote() { return note; }
    public void setNote(String v) { note=v; }
    public String getClientRequestId() { return clientRequestId; }
    public void setClientRequestId(String v) { clientRequestId=v; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime v) { createdAt=v; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime v) { updatedAt=v; }
    public Integer getDeleted() { return deleted; }
    public void setDeleted(Integer v) { deleted=v; }
}
