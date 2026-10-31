-- PRP MCP G0 review: sanitized Keycloak realm/client/scope inventory.
-- ONLY SELECT within a PostgreSQL READ ONLY transaction. No credentials,
-- secrets, user names, key material, JSON policies, token values, or writes.
-- Execute only against the operator-selected isolated Keycloak PostgreSQL.
-- Database field names match Keycloak 26.8's Realm/Client/ClientScope schema.
BEGIN TRANSACTION READ ONLY;

SELECT 'REALM_MATCH_COUNT' AS check_name, COUNT(*)::text AS observed
FROM realm WHERE name = 'prp-mcp';

SELECT 'EXISTING_REALM_CLIENT_COUNT' AS check_name, COUNT(c.id)::text AS observed
FROM realm r
LEFT JOIN client c ON c.realm_id = r.id
WHERE r.name = 'prp-mcp';

WITH required(scope_name) AS (
  VALUES ('basic'), ('prp.tasks.read'), ('offline_access')
)
SELECT 'CLIENT_SCOPE_' || req.scope_name AS check_name,
       CASE COUNT(cs.id)
         WHEN 0 THEN 'MISSING'
         WHEN 1 THEN 'PRESENT'
         ELSE 'DUPLICATE_REVIEW'
       END AS observed
FROM required req
LEFT JOIN realm r ON r.name = 'prp-mcp'
LEFT JOIN client_scope cs
  ON cs.realm_id = r.id
 AND cs.name = req.scope_name
GROUP BY req.scope_name
ORDER BY req.scope_name;

WITH required(client_id) AS (
  VALUES
  ('https://chatgpt.com/oauth/client.json'),
  ('prp-first-party-link')
)
SELECT 'CLIENT_' || req.client_id AS check_name,
       CASE COUNT(c.id)
         WHEN 0 THEN 'MISSING'
         WHEN 1 THEN 'PRESENT_REVIEW_SHAPE'
         ELSE 'DUPLICATE_REVIEW'
       END AS observed
FROM required req
LEFT JOIN realm r ON r.name = 'prp-mcp'
LEFT JOIN client c
  ON c.realm_id = r.id
 AND c.client_id = req.client_id
GROUP BY req.client_id
ORDER BY req.client_id;

COMMIT;
