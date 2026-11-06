# Production health CIMD candidate ¡ª NOT installed

Separate opt-in module. Existing production Dockerfile, Realm generator, application,
SQL, controller, Nginx and deployment workflows remain unchanged. Merging main can
still trigger the repository normal application release; this Draft is NOT merge approval.

The metadata executor accepts only the reviewed ChatGPT metadata and JWKS HTTPS URLs,
normalizes only token_endpoint_auth_methods_supported before strict native DTO parsing,
and retains native private_key_jwt verification. The persistence provider keeps basic
as the sole default scope and health capabilities optional; it does not write consent.
Use together with the existing exact health client condition and request executor.
Do not advertise CIMD without installing and verifying actual support.

## Isolated evidence (2026-11-06, not CI evidence)

Java metadata cases: 14/14. Actual Keycloak client identification/refusals: 7/7.
Actual synthetic-user code+S256+private_key_jwt, signed claims, read-only scope,
wrong signature/verifier/callback/audience, code replay, refresh and revoked-refresh:
21/21. The signer and TLS CA were disposable laboratory substitutions, never real
ChatGPT credentials. The laboratory returned to official JWKS and was backed up/stopped.
Experimental OCI ID: sha256:018251f895ee1a4c271d0fd182409b8f1d335aebada27d13a60966cb22c0519c.
This local image is not an approved production artifact.

## Required candidate configuration (review only)

Enable `resource-indicators,cimd:v1`. Register BOTH service-provider files.
Select provider using
`--spi-client-policy-executor--prp-health-cimd-metadata--cimd-provider-name=prp-health-scope-cimd`.
Add metadata executor BEFORE the existing exact health request executor. Its reviewed
configuration is cimd-allow-http-scheme=false, cimd-allow-permitted-domains=[chatgpt.com,
persistent.oaistatic.com], cimd-restrict-same-domain=false, only-allow-confidential-client=true,
cimd-resource-indicator-allow-list=[https://micor.top/api/mcp]. Exact URL checks in code
remain required; the logo domain is not an allowed egress destination. No DCR endpoint.
Never widen default scopes, disable consent or substitute client_secret_basic/none.

## Still blocked

Real ChatGPT managed signing and production business isolation are unverified.
Production pre-registered-client adoption must be rehearsed with existing identity,
consent and signing-key state: native clients lacking CIMD cache state may use CREATE
and encounter a duplicate identifier. Do not delete/recreate production clients or users.
Require fresh production PostgreSQL backup+actual isolated restore, image provenance,
complete CI/review and explicit production switch approval. No installer is included.
