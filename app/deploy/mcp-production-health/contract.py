"""Fixed reviewed candidate identities; no installation or secrets."""
REALM = 'prp-mcp-prod'
ISSUER = 'https://auth.micor.top/realms/' + REALM
RESOURCE = 'https://micor.top/api/mcp'
CLIENT = 'https://chatgpt.com/oauth/client.json'
JWKS = 'https://chatgpt.com/oauth/jwks.json'
REDIRECT = 'https://chatgpt.com/connector_platform_oauth_redirect'
FIRST_PARTY = 'prp-production-identity-link'
FIRST_REDIRECT = 'https://micor.top/prp/me/mcp-link/callback'
SCOPES = ('prp.wellness.read', 'prp.wellness.write.create', 'prp.wellness.write.update',
          'prp.wellness.write.delete', 'prp.wellness.write.status', 'prp.wellness.write.confirm')
