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
  ["production OAuth issuer", {issuer_url: "https://auth.micor.top/realms/prp-mcp218"}],
  ["production OAuth endpoint as resource", {resource_url: "https://auth.micor.top/api/mcp"}],
  ["other project preview resource", {resource_url: "https://pos-preview.micor.top/api/mcp"}],
  ["other project preview issuer", {issuer_url: "https://auth-pos-preview.micor.top/realms/prp-mcp218"}],
  ["unrelated resource with valid HTTPS", {resource_url: "https://another-prp-stage.micor.top/api/mcp"}],
  ["unrelated issuer with valid HTTPS", {issuer_url: "https://auth-another-prp-stage.micor.top/realms/prp-mcp218"}],
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


// Exercise the actual CLI contract, not only the exported validation function.
// This uses temporary non-secret files inside the ephemeral CI worker. No network,
// Docker, server, grant or application data is touched.
import { spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const commandPath = fileURLToPath(new URL("./mcp218-canary-plan.mjs", import.meta.url));

function runOfflineCli(contents) {
  const directory = mkdtempSync(join(tmpdir(), "mcp218-plan-ci-"));
  try {
    const planFile = join(directory, "plan.json");
    writeFileSync(planFile, contents, { mode: 0o600 });
    const outcome = spawnSync(process.execPath, [commandPath, planFile], {
      encoding: "utf8",
      timeout: 10000,
      env: { ...process.env, NO_PROXY: "*", HTTP_PROXY: "", HTTPS_PROXY: "" },
    });
    assert.equal(outcome.error, undefined);
    return outcome;
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

test("CLI: valid preparation plan is explicitly NOT release authorization", () => {
  const outcome = runOfflineCli(JSON.stringify(proposed));
  assert.equal(outcome.status, 0);
  assert.match(outcome.stdout, /^MCP218_PLAN_SHAPE_PASS_ONLY_NO_DEPLOY_AUTHORIZATION\s*$/);
  assert.equal(outcome.stderr, "");
});

test("CLI: shared V2 domain must fail closed with fixed error code", () => {
  const outcome = runOfflineCli(JSON.stringify({
    ...proposed, resource_url: "https://prp-test.micor.top/api/mcp",
  }));
  assert.equal(outcome.status, 2);
  assert.match(outcome.stderr, /^MCP218_PLAN_NO_GO NEW_HTTPS_RESOURCE_REQUIRED\s*$/);
  assert.equal(outcome.stdout, "");
});

test("CLI: unknown secret-bearing field is rejected without echoing its value", () => {
  const sensitiveSentinel = "DO_NOT_PRINT_CI_SENTINEL_8f5be7";
  const outcome = runOfflineCli(JSON.stringify({
    ...proposed, client_secret: sensitiveSentinel,
  }));
  assert.equal(outcome.status, 2);
  assert.match(outcome.stderr, /^MCP218_PLAN_NO_GO UNEXPECTED_FIELD\s*$/);
  assert.ok(!outcome.stdout.includes(sensitiveSentinel));
  assert.ok(!outcome.stderr.includes(sensitiveSentinel));
});

test("CLI: malformed JSON cannot be accepted as an empty permission set", () => {
  const outcome = runOfflineCli("{ not valid JSON: ");
  assert.equal(outcome.status, 2);
  assert.match(outcome.stderr, /^MCP218_PLAN_NO_GO INVALID_OR_UNREADABLE_JSON\s*$/);
  assert.equal(outcome.stdout, "");
});
