"""Fixed reviewed candidate identities; no installation or secrets."""
REALM = 'prp-mcp-prod'
ISSUER = 'https://auth.micor.top/realms/' + REALM
RESOURCE = 'https://micor.top/api/mcp'
CLIENT = 'https://chatgpt.com/oauth/client.json'
JWKS = 'https://chatgpt.com/oauth/jwks.json'
REDIRECT = 'https://chatgpt.com/connector_platform_oauth_redirect'
# Client IDs may match across independent Realms; issuer, key and callback do not.
# Retain the frontend's already-reviewed exact first-party client-ID contract.
FIRST_PARTY = 'prp-first-party-link'
FIRST_REDIRECT = 'https://micor.top/prp/me/mcp-link/callback'
SCOPES = ('prp.wellness.read', 'prp.wellness.write.create', 'prp.wellness.write.update',
          'prp.wellness.write.delete', 'prp.wellness.write.status', 'prp.wellness.write.confirm')
