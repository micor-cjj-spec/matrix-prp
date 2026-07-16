package com.matrix.prp.finance.repository;

import com.matrix.prp.finance.model.CreateFinanceAccountRequest;
import com.matrix.prp.finance.model.CreateFinanceCategoryRequest;
import com.matrix.prp.finance.model.FinanceAccountItem;
import com.matrix.prp.finance.model.FinanceCategoryItem;
import java.util.List;

public interface FinanceConfigRepository {

    List<FinanceAccountItem> listAccounts();

    FinanceAccountItem createAccount(CreateFinanceAccountRequest request);

    FinanceAccountItem updateAccount(long id, CreateFinanceAccountRequest request);

    void deleteAccount(long id);

    List<FinanceCategoryItem> listCategories(String type);

    FinanceCategoryItem createCategory(CreateFinanceCategoryRequest request);

    FinanceCategoryItem updateCategory(long id, CreateFinanceCategoryRequest request);

    void deleteCategory(long id);
}
