-- V18: additive AI conversation-management metadata. Preserve all existing chats and cards.
ALTER TABLE prp_ai_conversations
  ADD COLUMN deleted_at DATETIME(6) NULL,
  ADD COLUMN title_source VARCHAR(16) NOT NULL DEFAULT 'AUTO',
  ADD COLUMN is_pinned TINYINT(1) NOT NULL DEFAULT 0;

CREATE INDEX idx_ai_conversations_active_page
  ON prp_ai_conversations(user_id, deleted_at, updated_at, id);
