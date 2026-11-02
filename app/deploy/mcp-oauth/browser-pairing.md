# PRP first-party browser OAuth pairing (draft; disabled by default)

This is an optional first-party pairing UX for iPhone Safari/PWA and desktop.
It is **not** the ChatGPT connector OAuth client and does not replace the
existing secure PRP `/api/mcp/link` token + one-use ticket checks. It only
solves the prerequisite: linking a verified Keycloak `iss/sub` to a PRP owner.
Once paired, ChatGPT must be authorized **separately** using its **own**
trusted OAuth client ID and task-only permissions.

## Prerequisites before allowing the browser button

A separate **public Keycloak Authorization Code / S256** pairing client must
be registered by an authorized administrator through the approved on-host
change controller. Do not alter the live Realm until the fresh B2 restore and
Nginx installation approval evidence exists. Do not reuse
`https://chatgpt.com/oauth/client.json`, let ChatGPT sign browser requests,
enable DCR, or add `prp.finance.read`, wellness or write permissions.

Review these exact client settings in an isolated restored Keycloak 26.8 Realm:

| Property | Expected |
| --- | --- |
| Client ID | `prp-browser-link` (or another reviewed **separate** stable ID) |
| Client type | Public (client authentication OFF) |
| Grant type | Standard authorization code ON; implicit/password/service account OFF |
| PKCE | Required S256; reject missing/plain |
| Valid redirect URI | Exact **deployed PRP Web/PWA** URL ending `/me/mcp-clients`, no query/wildcards |
| Web Origins (CORS) | Exact `https://<PRP Web hostname>`, no `*` |
| Full Scope Allowed | OFF |
| Default scopes | `basic` containing access-token `sub` mapper |
| Optional scopes | **Only** `prp.tasks.read` |
| Audience mapper | `included.custom.audience` = exact public MCP `https://<PRP MCP host>/api/mcp` |
| OAuth resource indicator | Must accept that exact registered Resource URI |
| Token endpoint | Allow trusted PRP Web origin for cross-origin PKCE token exchange |
| Consent | ON, display task-read grant clearly |
| Access token | Short-lived, signed RS256, verified on PRP server before link |
| Refresh/offline access | Not requested/granted to the browser pairing client |

The same client must not retain `prp.tasks.read` permission within PRP:
the pairing wizard calls the dedicated owner-only
`POST /api/mcp/clients/pairing` endpoint to issue a **server-enforced
10-minute, task-read-only lease**. V28 creates the separate empty
`prp_mcp_pairing_grant_leases` companion table, without altering existing
`prp_mcp_client_grants` rows. Every subsequent bearer request joins that
lease using MySQL's current clock: expiration immediately denies the bearer,
even after a browser crash or lost `sessionStorage`.

The wizard submits the existing hashed one-time ticket and also attempts
to revoke the lease on **success or failure**, for earlier cutoff. If the
owner cancels, the callback fails, or the token exchange/PRP link is rejected,
the browser must revoke the temporary grant. A cancelled/incomplete same-tab
session remains discoverable on revisiting the owner page; the UI provides
**Cancel pairing and revoke**, and automatically cancels requests whose stored
9-minute deadline has elapsed. Never imply that the local ticket expiry itself
expires the separate PRP **client grant**; it does not.

If the browser never returns (lost tab/session, crashed PWA) or a network outage
prevents manual revocation, the lease automatically becomes ineffective after
10 minutes; the database retains an `EXPIRED` record for owner visibility.
The PRP owner can still go to **Registered clients** and manually revoke
the separate pairing client's read permission immediately. The UI surfaces
an explicit danger warning when its automatic revocation call fails.

## Front-end opt-in deployment settings

Only after the separate client, Keycloak CORS, PRP public staging Web and
`/api/mcp/link` guarded route have been tested, build the **staging** Web with:

```sh
VITE_MCP_PAIRING_ISSUER=https://auth-test.micor.top/realms/prp-mcp
VITE_MCP_PAIRING_CLIENT_ID=prp-browser-link
VITE_MCP_PAIRING_RESOURCE=https://prp-test.micor.top/api/mcp
```

Values are public identifiers, **never secrets**. The SPA calculates its
exact redirect URI from the actual deployed `VITE_APP_BASE` and browser
origin. For example, *only if the staging Web is truly deployed there*,
`https://prp-test.micor.top/prp/me/mcp-clients`. Do not assume that staging
has a Web/PWA deployment because `/api/mcp` is reachable: check the
actual routing and `/prp/` history fallback first.

Without all three settings, the optional browser button stays hidden and
the existing operator/CLI pairing path remains unchanged. A missing or
unsafe configuration must not silently activate a public OAuth client.

## User experience and security

1. PRP user logs in and selects `我的 → MCP 客户端授权`.
2. The new browser pairing section asks for a PRP password, then narrowly
   grants the separate pairing client `prp.tasks.read` and creates the
   10-minute one-use, client-bound ticket using existing PRP APIs.
3. The browser generates a cryptographically random PKCE S256 verifier
   and `state` and saves only `state/verifier/ticket` in **tab-scoped
   sessionStorage**. It redirects in the same tab to the pinned Keycloak
   issuer. The ticket and verifier never appear in the authorization URL.
4. After Keycloak login and consent, the PRP SPA must receive an exact
   `code/state/iss` callback. It immediately removes the authorization
   query from the address bar, consumes the pending session once and checks
   the 9-minute bound, issuer and `state` before the token exchange.
5. The browser sends the code/verifier **only to the configured Keycloak
   token endpoint** using the exact resource and a public client ID. The
   bearer token is never put in local/sessionStorage, URL or ordinary chat.
6. It calls **PRP** `POST /api/mcp/link` with the transient Keycloak bearer
   and owner-issued ticket. PRP's independent JWT decoder verifies issuer,
   signature, timestamps, resource audience and signed client identity;
   the linking service checks the ticket's PRP owner, client and one-time use.
7. Once the link is confirmed, PRP revokes the temporary pairing client's
   grant. Verify the issuer/subject remains linked to PRP before authorizing
   ChatGPT's distinct client for read-only tasks.

The HTML app uses `Referrer-Policy: no-referrer` to prevent OAuth query codes
from leaking into requests for same-origin assets. Nginx should additionally
set `Referrer-Policy: no-referrer` on the OAuth callback path, and never
persist authorization query strings in proxy logs.

The browser's `sessionStorage` must survive the **same-tab** Keycloak
redirect. Some in-app iOS browsers or separate tabs isolate storage; if the
tab/session is replaced, the flow fails closed and must be restarted. The
OAuth code and ticket cannot be recovered from the chat.

## Isolated acceptance

- Node tests: URL constraints, scope minimization, random S256, state,
  issuer, callback, expiry and error rejection.
- Vue TypeScript build at `/` and `/prp/`.
- Disposable Keycloak 26.8 + Nginx TLS + PRP Java + MySQL:
  public S256 browser client gets an exact-resource signed token; cannot read
  tools before PRP identity linking; owner links with a one-use ticket; ticket
  replay fails; public client grant revoked while the account link remains.
- Complete CI for the MCP development branch after integration.
- **Separate real mobile Safari/PWA test required**. A Python browser-shaped
  request or GitHub CI cannot prove iOS sessionStorage, WebKit CORS/cookies,
  public DNS, certificate behavior, or actual ChatGPT connectivity.

**Do not install the live Realm client, deploy PRP, merge the MCP release
candidate into `main`, or open Keycloak admin publicly until all existing
guarded B2 backup/restore and Nginx approval steps pass.**

## Authentication loss during OAuth callback

If the original PRP session expired while the browser visited Keycloak,
Vue Router sends the user to the PRP login page **without** copying OAuth
`code`, `state`, or `iss` into the `redirect` URL. The incomplete
authorization code must **not** be reused after a fresh PRP login; the user
returns to MCP Client Authorization to cancel and revoke the pending public
client grant, and can then initiate a new pairing with a fresh ticket/state.

A passing isolated E2E alone does not establish that every iOS PWA process
retains `sessionStorage` across Keycloak login. If persistence is lost,
fail closed rather than weakening callback state/issuer validation.
