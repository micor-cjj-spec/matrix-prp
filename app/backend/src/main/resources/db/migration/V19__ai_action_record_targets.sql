-- V19: additive action -> real record links, preserving V1..V18 historical row layouts.
-- The business record remains authoritative after the AI draft has been consumed.
CREATE TABLE prp_wellness_ai_action_targets (
  draft_id CHAR(36) NOT NULL,
  user_id BIGINT NOT NULL,
  ordinal INT NOT NULL,
  target_type VARCHAR(16) NOT NULL,
  record_id BIGINT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(draft_id, ordinal),
  INDEX idx_ai_action_target_owner (user_id, draft_id),
  CONSTRAINT fk_ai_action_target_draft FOREIGN KEY (draft_id)
    REFERENCES prp_wellness_ai_drafts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Backfill previously saved meal drafts using ONLY the durable idempotency keys.
-- No inference by date/meal type, which could bind a link to an unrelated meal.
INSERT INTO prp_wellness_ai_action_targets (draft_id,user_id,ordinal,target_type,record_id)
SELECT d.id,d.user_id,
       CASE WHEN m.idempotency_key=d.id THEN 0
            ELSE CAST(SUBSTRING(m.idempotency_key,38) AS UNSIGNED) END,
       'meal',m.id
FROM prp_wellness_ai_drafts d
JOIN prp_wellness_meals m ON m.user_id=d.user_id
WHERE d.status='CONSUMED'
  AND (m.idempotency_key=d.id OR
       (m.idempotency_key LIKE CONCAT(d.id,'-%')
        AND SUBSTRING(m.idempotency_key,38) REGEXP '^[0-9]+$'));
