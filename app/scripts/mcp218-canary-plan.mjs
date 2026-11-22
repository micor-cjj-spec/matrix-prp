// #218: syntax-only preparation guard; never performs network calls or deploys.
// A passing result means plan shape only, NOT staging approval or verified isolation.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export function checkCanaryPlan(plan) {
  if (!plan || typeof plan !== "object" || Array.isArray(plan)) return ["PLAN_OBJECT_REQUIRED"];
  const issues = [];
  const fields = ["purpose","release_gate","project","resource_url","issuer_url","mysql_schema","mysql_volume","keycloak_volume","database_source","keycloak_source","data_policy","published","mcp_enabled","oauth_enabled","write_enabled","additional_read_tools_enabled","review_video_read_tools_enabled","advertised_scopes","expected_tools"];
  for (const name of Object.keys(plan)) if (!fields.includes(name)) issues.push("UNEXPECTED_FIELD");
  const exact = {purpose:"mcp218-review-video-readonly",release_gate:"PREPARATION_ONLY",database_source:"new-empty",keycloak_source:"new-empty",data_policy:"synthetic-only",published:false,mcp_enabled:false,oauth_enabled:false,write_enabled:false,additional_read_tools_enabled:false,review_video_read_tools_enabled:false};
  for (const [key,value] of Object.entries(exact)) if(plan[key]!==value) issues.push("INVALID_"+key.toUpperCase());
  const validName = (name,regex) => typeof name === "string" && regex.test(name);
  if(!validName(plan.project,/^prp-mcp218-[a-z0-9]+(?:-[a-z0-9]+)*$/)) issues.push("ISOLATED_PROJECT_REQUIRED");
  if(!validName(plan.mysql_schema,/^matrix_prp_mcp218_[a-z0-9_]+$/)) issues.push("ISOLATED_MYSQL_SCHEMA_REQUIRED");
  if(!validName(plan.mysql_volume,/^mcp218_[a-z0-9_]+$/)||!validName(plan.keycloak_volume,/^mcp218_[a-z0-9_]+$/)||plan.mysql_volume===plan.keycloak_volume) issues.push("DISTINCT_ISOLATED_VOLUMES_REQUIRED");
  const scopeNames=["prp.reviews.read","prp.video.read"];
  const toolNames=["prp_reviews_list","prp_video_folders","prp_video_progress"];
  function exactArray(value, expected) {
    return Array.isArray(value) && value.length===expected.length &&
      expected.every(item => value.includes(item)) && new Set(value).size===expected.length;
  }
  if(!exactArray(plan.advertised_scopes,scopeNames)) issues.push("EXACT_READ_SCOPE_SET_REQUIRED");
  if(!exactArray(plan.expected_tools,toolNames)) issues.push("EXACT_THREE_READ_TOOLS_REQUIRED");
  function endpoint(value,suffix) {
    if(typeof value!=="string") return null;
    const prefix="https://";
    if(!value.startsWith(prefix)||!value.endsWith(suffix)) return null;
    const host=value.slice(prefix.length,-suffix.length);
    if(host.includes("/")||host.includes(":")||host.includes("@")||host.includes("?")||host.includes("#"))return null;
    const labels=host.split(".");
    if(labels.length<2||labels.some(x=>!(/^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(x))))return null;
    const banned=new Set(["micor.top","www.micor.top","api.micor.top","prp.micor.top","prp-test.micor.top","auth-test.micor.top","localhost"]);
    if(banned.has(host)||/\.(invalid|example|test|localhost|local)$/.test(host))return null;
    if(/^[0-9.]+$/.test(host))return null;
    return host;
  }
  const resource=endpoint(plan.resource_url,"/api/mcp");
  const issuer=endpoint(plan.issuer_url,"/realms/prp-mcp218");
  if(!resource)issues.push("NEW_HTTPS_RESOURCE_REQUIRED");
  if(!issuer)issues.push("NEW_HTTPS_ISSUER_REQUIRED");
  if(resource&&issuer&&resource===issuer)issues.push("SEPARATE_ISSUER_REQUIRED");
  return [...new Set(issues)].sort();
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  try {
    if (process.argv.length !== 3) throw new Error("PLAN_PATH_REQUIRED");
    const plan=JSON.parse(readFileSync(process.argv[2],"utf8"));
    const violations=checkCanaryPlan(plan);
    if (violations.length) {
      // Print only fixed violation codes. Never dump raw config, secrets or paths.
      console.error("MCP218_PLAN_NO_GO " + violations.join(","));
      process.exitCode=2;
    } else {
      console.log("MCP218_PLAN_SHAPE_PASS_ONLY_NO_DEPLOY_AUTHORIZATION");
    }
  } catch {
    console.error("MCP218_PLAN_NO_GO INVALID_OR_UNREADABLE_JSON");
    process.exitCode=2;
  }
}
