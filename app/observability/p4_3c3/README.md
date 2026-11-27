# P4.3C.3 — Tunnel compatibility candidate (offline only)

Nested Draft against exact #495 4891cbed14316d92f6a191e35d059b1620fa1525.
Do not merge or deploy. The original #424 and #495 files remain immutable
except this branch's PR-only workflow extension. No runtime launcher.

- Reuse #495 materializer, hash-locked MCP SDK 2.3.0, bounded ASGI, owner
  gateway, #424 root-owned profile and grant. Run the unchanged direct
  regression first; materialize a separate Tunnel-only candidate.
- Version 2 root-approved profile adds exactly privateOrigin (HTTPS DNS
  authority, optional exact non-default port). Resource is exact external
  HTTPS DNS /v1/mcp/tunnel_<32 lowercase hex> for the observed legacy-ID
  form. No query, fragments, userinfo, wildcard, alternate audience or
  arbitrary paths. The approved profile digest binds the entire URI and
  private origin; issuer, external host and private host are distinct.
  Synthetic examples only; no real host, tunnel ID, secret or owner subject.
- SDK auth resource and verifier retain external resource; actual ingress
  accepts only the private Host and existing /mcp and private metadata
  paths. Internal fixed metadata GET alias to SDK-generated route and
  exact SDK challenge metadata URL replacement; no header-controlled
  routing or public connector endpoint on private ingress. Keep SDK
  validate_token_resource=True and exact RFC7662 audience/scope/issuer/
  subject/client/grant checks unchanged. SDK metadata still names the
  external resource. No token or scope expansion.
- CI adapts the existing actual SDK + synthetic introspection regression
  to distinct origin and port, extends wrong/extra audience, Host, path,
  digest, malformed profile, duplicate headers and forwarded-host cases.
  Existing baseline tests and dependency job stay intact.
- Official docs: https://github.com/openai/tunnel-client/blob/master/docs/configuration.md
  describes PRMD and challenge rewriting; https://github.com/openai/tunnel-client/blob/master/docs/connectors.md
  describes private HTTP forwarding. Actual external connector origin,
  discovery resource/Host/CA, token scope and audience issuance, and
  actual tunnel-client version/transport remain unverified. Do not guess
  a real profile or install from synthetic evidence. Live readiness also
  needs independent security review, fresh resource/recovery evidence,
  P1 closure and explicit approval. No real network issuer, tunnel,
  admin/config change, service, credentials, production release or merge.
