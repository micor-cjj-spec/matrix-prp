package com.matrix.prp.finance.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.common.api.ResourceNotFoundException;
import com.matrix.prp.finance.entity.FinanceAccountEntity;
import com.matrix.prp.finance.entity.FinanceTransactionEntity;
import com.matrix.prp.finance.entity.FinanceTransferEntity;
import com.matrix.prp.finance.mapper.FinanceAccountMapper;
import com.matrix.prp.finance.mapper.FinanceTransactionMapper;
import com.matrix.prp.finance.mapper.FinanceTransferMapper;
import com.matrix.prp.finance.model.CreateFinanceTransferRequest;
import com.matrix.prp.finance.model.FinanceAccountBalance;
import com.matrix.prp.finance.model.FinanceTransferItem;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
@Profile("!test")
public class FinanceLedgerService {
    private final FinanceAccountMapper accounts;
    private final FinanceTransactionMapper transactions;
    private final FinanceTransferMapper transfers;

    public FinanceLedgerService(FinanceAccountMapper accounts,
                                FinanceTransactionMapper transactions,
                                FinanceTransferMapper transfers) {
        this.accounts=accounts; this.transactions=transactions; this.transfers=transfers;
    }

    private FinanceAccountEntity owned(long id) {
        FinanceAccountEntity a=accounts.selectById(id);
        if(a==null || !Objects.equals(a.getUserId(),CurrentUser.id()))
            throw new ResourceNotFoundException("Finance account not found: "+id);
        return a;
    }

    private List<FinanceTransferEntity> ownedTransfers() {
        return transfers.selectList(new LambdaQueryWrapper<FinanceTransferEntity>()
                .eq(FinanceTransferEntity::getUserId, CurrentUser.id())
                .orderByDesc(FinanceTransferEntity::getTransferDate)
                .orderByDesc(FinanceTransferEntity::getId));
    }

    private FinanceTransferItem item(FinanceTransferEntity t, Map<Long, FinanceAccountEntity> accountsById) {
        FinanceAccountEntity from=accountsById.get(t.getFromAccountId());
        FinanceAccountEntity to=accountsById.get(t.getToAccountId());
        return new FinanceTransferItem(t.getId(),t.getFromAccountId(),
                from==null?"已删除账户":from.getName(),t.getToAccountId(),
                to==null?"已删除账户":to.getName(),t.getAmount(),
                from==null?"CNY":from.getCurrency(),t.getTransferDate(),t.getNote());
    }

    private Map<Long,FinanceAccountEntity> allAccountIds() {
        Map<Long,FinanceAccountEntity> result=new HashMap<>();
        accounts.selectList(new LambdaQueryWrapper<FinanceAccountEntity>()
                .eq(FinanceAccountEntity::getUserId,CurrentUser.id()))
                .forEach(a->result.put(a.getId(),a));
        return result;
    }

    public List<FinanceTransferItem> listTransfers() {
        var indexed=allAccountIds();
        return ownedTransfers().stream().map(t->item(t,indexed)).toList();
    }

    @Transactional
    public FinanceTransferItem createTransfer(CreateFinanceTransferRequest request) {
        if (Objects.equals(request.fromAccountId(),request.toAccountId()))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Cannot transfer to same account");
        FinanceAccountEntity from=owned(request.fromAccountId());
        FinanceAccountEntity to=owned(request.toAccountId());
        if (!Objects.equals(from.getCurrency(),to.getCurrency()))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Currency conversion is not supported");
        if(request.transferDate()!=null && request.transferDate().isAfter(LocalDate.now()))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Future-dated transfers are not supported");

        // Client retry must not move funds twice. DB unique key also prevents concurrent duplicates.
        FinanceTransferEntity existing=transfers.selectOne(new LambdaQueryWrapper<FinanceTransferEntity>()
                .eq(FinanceTransferEntity::getUserId,CurrentUser.id())
                .eq(FinanceTransferEntity::getClientRequestId,request.clientRequestId()));
        if(existing!=null) {
            if(!Objects.equals(existing.getFromAccountId(),request.fromAccountId())
                    || !Objects.equals(existing.getToAccountId(),request.toAccountId())
                    || existing.getAmount().compareTo(request.amount())!=0
                    || !Objects.equals(existing.getTransferDate(),
                        request.transferDate()==null?LocalDate.now():request.transferDate())
                    || !Objects.equals(existing.getNote(),request.note()==null?"":request.note()))
                throw new ResponseStatusException(HttpStatus.CONFLICT,"Idempotency key reused with different transfer");
            return item(existing,Map.of(from.getId(),from,to.getId(),to));
        }
        FinanceTransferEntity t=new FinanceTransferEntity();
        t.setUserId(CurrentUser.id());
        t.setFromAccountId(from.getId());
        t.setToAccountId(to.getId());
        t.setAmount(request.amount());
        t.setTransferDate(request.transferDate()==null?LocalDate.now():request.transferDate());
        t.setNote(request.note()==null?"":request.note());
        t.setClientRequestId(request.clientRequestId());
        t.setCreatedAt(LocalDateTime.now()); t.setUpdatedAt(t.getCreatedAt()); t.setDeleted(0);
        try { transfers.insert(t); }
        catch (org.springframework.dao.DuplicateKeyException collision) {
            throw new ResponseStatusException(HttpStatus.CONFLICT,
                    "This transfer request was already recorded; refresh transfers before retrying", collision);
        }
        return item(t,Map.of(from.getId(),from,to.getId(),to));
    }

    @Transactional
    public void deleteTransfer(long id) {
        FinanceTransferEntity t=transfers.selectById(id);
        if(t==null || !Objects.equals(t.getUserId(),CurrentUser.id()))
            throw new ResourceNotFoundException("Finance transfer not found: "+id);
        transfers.deleteById(id);
    }

    /** All-time actual book balance, not monthly net flow. No FX conversion or automatic bank sync. */
    public List<FinanceAccountBalance> accountBalances() {
        Map<Long,FinanceAccountEntity> indexed=allAccountIds();
        Map<Long,BigDecimal[]> sums=new HashMap<>();
        indexed.keySet().forEach(id->sums.put(id,new BigDecimal[]{
                BigDecimal.ZERO,BigDecimal.ZERO,BigDecimal.ZERO,BigDecimal.ZERO}));
        transactions.selectList(new LambdaQueryWrapper<FinanceTransactionEntity>()
                .eq(FinanceTransactionEntity::getUserId,CurrentUser.id())
                .le(FinanceTransactionEntity::getTransactionDate,LocalDate.now()))
                .forEach(t->{
                    BigDecimal[] s=sums.get(t.getAccountId());
                    if(s!=null) s["income".equals(t.getType())?0:1]=s["income".equals(t.getType())?0:1].add(t.getAmount());
                });
        transfers.selectList(new LambdaQueryWrapper<FinanceTransferEntity>()
                .eq(FinanceTransferEntity::getUserId,CurrentUser.id())
                .le(FinanceTransferEntity::getTransferDate,LocalDate.now()))
                .forEach(t->{
                    BigDecimal[] from=sums.get(t.getFromAccountId());
                    BigDecimal[] to=sums.get(t.getToAccountId());
                    if(from!=null) from[3]=from[3].add(t.getAmount());
                    if(to!=null) to[2]=to[2].add(t.getAmount());
                });
        return indexed.values().stream().sorted(java.util.Comparator.comparing(FinanceAccountEntity::getId))
                .map(a->{
                    BigDecimal[] s=sums.get(a.getId());
                    BigDecimal balance=a.getOpeningBalance().add(s[0]).subtract(s[1]).add(s[2]).subtract(s[3]);
                    return new FinanceAccountBalance(a.getId(),a.getName(),a.getCurrency(),
                            a.getOpeningBalance(),s[0],s[1],s[2],s[3],balance);
                }).toList();
    }
}
