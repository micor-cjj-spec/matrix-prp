package com.matrix.prp.finance.repository;

import com.matrix.prp.common.api.ResourceNotFoundException;
import com.matrix.prp.finance.model.CreateFinanceAccountRequest;
import com.matrix.prp.finance.model.CreateFinanceCategoryRequest;
import com.matrix.prp.finance.model.FinanceAccountItem;
import com.matrix.prp.finance.model.FinanceCategoryItem;
import java.time.OffsetDateTime;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;

@Repository
@Profile("test")
public class InMemoryFinanceConfigRepository implements FinanceConfigRepository {

    private final AtomicLong accountIdGenerator = new AtomicLong(7000);
    private final AtomicLong categoryIdGenerator = new AtomicLong(8000);
    private final CopyOnWriteArrayList<FinanceAccountItem> accounts = new CopyOnWriteArrayList<>();
    private final CopyOnWriteArrayList<FinanceCategoryItem> categories = new CopyOnWriteArrayList<>();

    @Override
    public List<FinanceAccountItem> listAccounts() {
        return accounts.stream()
                .sorted(Comparator.comparing(FinanceAccountItem::createdAt).reversed())
                .toList();
    }

    @Override
    public FinanceAccountItem createAccount(CreateFinanceAccountRequest request) {
        FinanceAccountItem account = new FinanceAccountItem(
                accountIdGenerator.incrementAndGet(),
                request.name(),
                defaultAccountType(request.type()),
                defaultCurrency(request.currency()),
                request.openingBalance(),
                defaultText(request.note()),
                OffsetDateTime.now());
        accounts.add(account);
        return account;
    }

    @Override
    public FinanceAccountItem updateAccount(long id, CreateFinanceAccountRequest request) {
        FinanceAccountItem existing = findAccount(id);
        FinanceAccountItem updated = new FinanceAccountItem(
                existing.id(),
                request.name(),
                defaultAccountType(request.type()),
                defaultCurrency(request.currency()),
                request.openingBalance(),
                defaultText(request.note()),
                existing.createdAt());
        accounts.remove(existing);
        accounts.add(updated);
        return updated;
    }

    @Override
    public void deleteAccount(long id) {
        boolean removed = accounts.removeIf(account -> account.id() == id);
        if (!removed) {
            throw new ResourceNotFoundException("Finance account not found: " + id);
        }
    }

    @Override
    public List<FinanceCategoryItem> listCategories(String type) {
        return categories.stream()
                .filter(category -> type == null || type.isBlank() || type.equals(category.type()))
                .sorted(Comparator.comparing(FinanceCategoryItem::createdAt).reversed())
                .toList();
    }

    @Override
    public FinanceCategoryItem createCategory(CreateFinanceCategoryRequest request) {
        FinanceCategoryItem category = new FinanceCategoryItem(
                categoryIdGenerator.incrementAndGet(),
                request.name(),
                request.type(),
                defaultColor(request.color()),
                defaultText(request.note()),
                OffsetDateTime.now());
        categories.add(category);
        return category;
    }

    @Override
    public FinanceCategoryItem updateCategory(long id, CreateFinanceCategoryRequest request) {
        FinanceCategoryItem existing = findCategory(id);
        FinanceCategoryItem updated = new FinanceCategoryItem(
                existing.id(),
                request.name(),
                request.type(),
                defaultColor(request.color()),
                defaultText(request.note()),
                existing.createdAt());
        categories.remove(existing);
        categories.add(updated);
        return updated;
    }

    @Override
    public void deleteCategory(long id) {
        boolean removed = categories.removeIf(category -> category.id() == id);
        if (!removed) {
            throw new ResourceNotFoundException("Finance category not found: " + id);
        }
    }

    private FinanceAccountItem findAccount(long id) {
        return accounts.stream()
                .filter(account -> account.id() == id)
                .findFirst()
                .orElseThrow(() -> new ResourceNotFoundException("Finance account not found: " + id));
    }

    private FinanceCategoryItem findCategory(long id) {
        return categories.stream()
                .filter(category -> category.id() == id)
                .findFirst()
                .orElseThrow(() -> new ResourceNotFoundException("Finance category not found: " + id));
    }

    private String defaultAccountType(String type) {
        return type == null || type.isBlank() ? "cash" : type;
    }

    private String defaultCurrency(String currency) {
        return currency == null || currency.isBlank() ? "CNY" : currency;
    }

    private String defaultColor(String color) {
        return color == null || color.isBlank() ? "#2563eb" : color;
    }

    private String defaultText(String value) {
        return value == null ? "" : value;
    }
}
