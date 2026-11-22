import test from "node:test";
import assert from "node:assert/strict";
import { checkCanaryPlan } from "./mcp218-canary-plan.mjs";

const proposed = {
  // Invented values for TESTS ONLY; these are not actual DNS or resource approvals.
  purpose: "mcp218-review-video-readonly",
  release_gate: "PREPARATION_ONLY",
  project: "prp-mcp218-ci-test",
  resource_url: "https://mcp218-ci-spec.micor.top/api/mcp",
  issuer_url: "https://auth-mcp218-ci-spec.micor.top/realms/prp-mcp218",
  mysql_schema: "matrix_prp_mcp218_ci",
  mysql_volume: "mcp218_mysql_ci",
  keycloak_volume: "mcp218_pg_ci",
  database_source: "new-empty",
  keycloak_source: "new-empty",
  data_policy: "synthetic-only",
  published: false,
  mcp_enabled: false,
  oauth_enabled: false,
  write_enabled: false,
  additional_read_tools_enabled: false,
  review_video_read_tools_enabled: false,
  advertised_scopes: ["prp.reviews.read", "prp.video.read"],
  expected_tools: ["prp_reviews_list", "prp_video_folders", "prp_video_progress"]
};

test("bounded non-deploy preparation plan passes shape check only", () => {
  assert.deepEqual(checkCanaryPlan(proposed), []);
});

const refused = [
  ["no plan", null],
  ["existing V2 project", {project: "prp-mcp-v2"}],
  ["legacy stage project", {project: "prp-mcp-stage"}],
  ["production schema", {mysql_schema: "matrix_prp"}],
  ["shared volume", {keycloak_volume: proposed.mysql_volume}],
  ["live public V2 resource", {resource_url: "https://prp-test.micor.top/api/mcp"}],
  ["live public test issuer", {issuer_url: "https://auth-test.micor.top/realms/prp-mcp218"}],
  ["insecure http", {resource_url: "http://mcp218-ci-spec.micor.top/api/mcp"}],
  ["wrong issuer path", {issuer_url: "https://auth-mcp218-ci-spec.micor.top/realms/prp-mcp"}],
  ["same issuer host", {issuer_url: "https://mcp218-ci-spec.micor.top/realms/prp-mcp218"}],
  ["dummy domain", {resource_url: "https://mcp218.example.invalid/api/mcp"}],
  ["data from original stage", {database_source: "reuse-v2"}],
  ["live data", {data_policy: "real-users"}],
  ["extra scopes", {advertised_scopes: ["prp.reviews.read","prp.video.read","prp.write.create"]}],
  ["duplicate scope", {advertised_scopes: ["prp.reviews.read","prp.reviews.read"]}],
  ["extra tool", {expected_tools: [...proposed.expected_tools, "prp_tasks_list"]}],
  ["missing tool", {expected_tools: ["prp_reviews_list","prp_video_folders"]}],
  ["writes enabled", {write_enabled: true}],
  ["other reads enabled", {additional_read_tools_enabled: true}],
  ["premature review video activation", {review_video_read_tools_enabled: true}],
  ["premature MCP activation", {mcp_enabled: true}],
  ["premature OAuth activation", {oauth_enabled: true}],
  ["premature public exposure", {published: true}],
  ["fake approval", {release_gate: "APPROVED_FOR_DEPLOY"}],
  ["secret field", {client_secret: "SHOULD_NOT_APPEAR_IN_FAILURE_MESSAGE"}]
];

for (const [name,delta] of refused) {
  test("NO-GO: " + name, () => {
    const value = delta === null ? null : {...proposed, ...delta};
    const errors = checkCanaryPlan(value);
    assert.ok(errors.length > 0);
    assert.ok(errors.every(item => /^[A-Z0-9_]+$/.test(item)));
    assert.ok(!errors.join(",").includes("SHOULD_NOT_APPEAR"));
  });
}
