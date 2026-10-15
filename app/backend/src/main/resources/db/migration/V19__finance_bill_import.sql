-- V19: additive import staging and exact-source deduplication; no ALTER/UPDATE to historical tables.
CREATE TABLE prp_finance_import_batches (
 id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
 user_id BIGINT NOT NULL,
 platform VARCHAR(24) NOT NULL,
 source_account_key VARCHAR(128) NOT NULL,
 original_filename VARCHAR(255) NOT NULL,
 sha256 CHAR(64) NOT NULL,
 status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
 created_at DATETIME(6) NOT NULL,
 updated_at DATETIME(6) NOT NULL,
 UNIQUE KEY uk_finance_import_file (user_id,platform,source_account_key,sha256),
 KEY idx_finance_import_user (user_id,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE prp_finance_import_rows (
 id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
 batch_id BIGINT NOT NULL,
 user_id BIGINT NOT NULL,
 source_line INT NOT NULL,
 source_transaction_id VARCHAR(128) NOT NULL,
 merchant_transaction_id VARCHAR(128) NOT NULL DEFAULT '',
 transaction_at DATETIME(6) NOT NULL,
 transaction_type VARCHAR(100) NOT NULL,
 counterparty VARCHAR(255) NOT NULL DEFAULT '',
 description TEXT NOT NULL,
 direction VARCHAR(24) NOT NULL,
 amount DECIMAL(18,2) NOT NULL,
 payment_method VARCHAR(128) NOT NULL DEFAULT '',
 original_status VARCHAR(100) NOT NULL DEFAULT '',
 note TEXT NOT NULL,
 row_status VARCHAR(24) NOT NULL,
 finance_transaction_id BIGINT NULL,
 created_at DATETIME(6) NOT NULL,
 UNIQUE KEY uk_finance_import_row (batch_id,source_line),
 KEY idx_finance_import_rows_batch (user_id,batch_id,row_status),
 CONSTRAINT fk_finance_import_row_batch FOREIGN KEY (batch_id)
   REFERENCES prp_finance_import_batches(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE prp_finance_source_links (
 id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
 user_id BIGINT NOT NULL,
 platform VARCHAR(24) NOT NULL,
 source_account_key VARCHAR(128) NOT NULL,
 source_transaction_id VARCHAR(128) NOT NULL,
 import_row_id BIGINT NOT NULL,
 finance_transaction_id BIGINT NOT NULL,
 created_at DATETIME(6) NOT NULL,
 UNIQUE KEY uk_finance_external_identity (user_id,platform,source_account_key,source_transaction_id),
 UNIQUE KEY uk_finance_source_row (import_row_id),
 UNIQUE KEY uk_finance_platform_global_id (user_id,platform,source_transaction_id),
 KEY idx_finance_source_transaction (user_id,finance_transaction_id),
 CONSTRAINT fk_finance_source_row FOREIGN KEY (import_row_id)
   REFERENCES prp_finance_import_rows(id),
 CONSTRAINT fk_finance_source_finance_txn FOREIGN KEY (finance_transaction_id)
   REFERENCES prp_finance_transactions(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
