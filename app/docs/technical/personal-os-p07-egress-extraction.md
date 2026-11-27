# P07.2–P07.3: review-only model egress and knowledge extraction activation

Baseline: c99a7e52c5e8957877435bb3ca07eb7a9365cac1 (#453, #465, #468).
Reuse #228 and P03-B2; no real endpoint call, host change, migration, release
authorization, MCP scope change or automatic memory confirmation.

## Model transport

The existing Java native and synchronous Spring AI HTTP clients now share a
model-only JDK HttpClient builder. The two Spring AI streaming adapters preserve
their default WebClient connector unless explicitly configured; when enabled
they use JdkClientHttpConnector with the same explicit HTTP CONNECT proxy.
No global JVM proxy, TLS trust override, fallback, credential change or retry
is added. Both environment settings absent/empty means disabled. Both must be
set to a valid proxy host and port for opt-in. Partial/malformed values fail
closed when the client is constructed. The existing provider catalog, consent,
one-attempt rules, and owner keys remain unchanged.

Review-only Squid policy: allow exactly one approved Backend source IP,
CONNECT to api.deepseek.com:443 only, deny private destinations and everything
else. Do not expose the proxy listener to host/public ports. The sample source
is a documentation address, not an actual deployment parameter. Future
separately approved setup requires a dedicated internal Backend-to-proxy
network with only those two participants, a separate proxy outbound network,
no direct Backend public route, and firewall enforcement against access from
MySQL/Gateway/other containers and private/reserved destinations. Keep DNS
resolution trusted; confirm current Squid package/version syntax and DNS/IP
ACL behavior before use. TLS terminates only at the provider. No interception.

On an approved nonproduction target only, configure
MATRIX_PRP_AI_EGRESS_PROXY_HOST and MATRIX_PRP_AI_EGRESS_PROXY_PORT using the
reviewed proxy address. Start with DeepSeek only. Proxy disabled/default-off
does not itself assert that direct outbound is blocked; network isolation is
required independently. Native and Spring AI CONNECT refusal is tested with
a loopback synthetic proxy. Successful TLS/SSE, Squid parse/runtime ACL
behavior, package provenance, IPv4/IPv6 routing and actual network isolation
remain separate nonproduction acceptance gates; do not claim these from CI.

## Chat extraction

Backend: MATRIX_PRP_PERSONAL_OS_CHAT_EXTRACTION_ENABLED (default false).
Staging web build argument: VITE_PERSONAL_OS_CHAT_EXTRACTION (default false).
Formal release web build: repository variable PRP_PERSONAL_OS_CHAT_EXTRACTION
must be exact true to produce true, otherwise false. Do not set it now.
Existing build/release hold remains unchanged. Web setting is build-time,
not runtime: separately approve exact artifact and both flags before activation.
A visible button does not authorize the backend. A backend flag does not make
candidate facts confirmed. Existing single-message preview, consent, one-use
token, source verification, restricted PENDING queue and separate owner
confirmation remain in place. Do not configure a global provider key.

## Evidence and rollout boundary

CI runs existing Maven/JUnit and deploy source contract tests. The new loopback
test exercises CONNECT refusal for the native and WebClient connector paths,
not a real provider. Before activation verify the exact build includes the
requested UI flag, backend default and active/disabled API behavior, actual
TLS/SSE with synthetic consent, proxy denials for unrelated domains/IP/ports,
and rollback with previous artifact/config. Keep V30 release independent;
do not merge or deploy this branch by implication.
