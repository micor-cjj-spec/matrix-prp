-- Time-bounded owner grants for first-party browser OAuth pairing only.
-- Existing permanent grants retain NULL (no change to their authorization).
-- An expired lease is denied at every request without a scheduler.
ALTER TABLE prp_mcp_client_grants
  ADD COLUMN expires_at TIMESTAMP NULL DEFAULT NULL AFTER status;
