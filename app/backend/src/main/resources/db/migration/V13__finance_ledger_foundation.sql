-- V13: additive personal finance ledger foundation. Requires V1-V12.
-- Preserve original amount, account snapshot, user ownership, and existing row IDs.
ALTER TABLE prp_finance_transactions
  ADD COLUMN account_id BIGINT NULL AFTER account,
  ADD INDEX idx_prp_finance_account_id (user_id, account_id, transaction_date);

-- Automatically register historical account labels with no active account record.
-- Zero opening balance is a placeholder: users must reconcile these legacy accounts.
INSERT INTO prp_finance_accounts
  (user_id, name, type, currency, opening_balance, note, created_at, updated_at, deleted)
SELECT t.user_id, t.account, 'cash', 'CNY', 0.00,
       '由历史收支流水自动补录；请核对期初余额', NOW(6), NOW(6), 0
FROM prp_finance_transactions t
LEFT JOIN prp_finance_accounts a
  ON a.user_id=t.user_id AND a.name=t.account AND a.deleted=0
WHERE t.deleted=0 AND a.id IS NULL
GROUP BY t.user_id, t.account;

-- Match by BOTH owner and historical label; no cross-user links.
UPDATE prp_finance_transactions t
INNER JOIN prp_finance_accounts a
  ON a.user_id=t.user_id AND a.name=t.account AND a.deleted=0
SET t.account_id=a.id
WHERE t.account_id IS NULL;

CREATE TABLE prp_finance_transfers (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  from_account_id BIGINT NOT NULL,
  to_account_id BIGINT NOT NULL,
  amount DECIMAL(18,2) NOT NULL,
  transfer_date DATE NOT NULL,
  note VARCHAR(500) NOT NULL DEFAULT '',
  client_request_id VARCHAR(64) NOT NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  deleted TINYINT NOT NULL DEFAULT 0,
  UNIQUE KEY uk_finance_transfer_idempotency (user_id,client_request_id),
  INDEX idx_finance_transfer_owner_date (user_id,transfer_date),
  INDEX idx_finance_transfer_from (user_id,from_account_id),
  INDEX idx_finance_transfer_to (user_id,to_account_id),
  CONSTRAINT fk_finance_transfer_from FOREIGN KEY (from_account_id) REFERENCES prp_finance_accounts(id),
  CONSTRAINT fk_finance_transfer_to FOREIGN KEY (to_account_id) REFERENCES prp_finance_accounts(id),
  CONSTRAINT chk_finance_transfer_accounts CHECK (from_account_id <> to_account_id),
  CONSTRAINT chk_finance_transfer_amount CHECK (amount > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
