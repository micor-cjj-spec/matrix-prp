#!/usr/bin/env node
/**
 * PRP GitHub-only release precheck.
 * Runs from protected main on an exact owner-authored Issue #323 comment.
 * NEVER authorizes, performs, or proves a production deployment.
 */
import {readFileSync, lstatSync, appendFileSync, writeFileSync} from 'node:fs'
import {resolve} from 'node:path'
import {fileURLToPath} from 'node:url'
import {execFileSync} from 'node:child_process'

export const REQUIRED_JOBS = Object.freeze([
  'backend-tests', 'web-build', 'mobile-build', 'db-migration-integration',
  'video-db-integration', 'deployment-gate-tests',
])
const SHA = /^[0-9a-f]{40}$/
const REQUEST = /^PRP-RELEASE-CHECK sha=([0-9a-f]{40})$/

export function parseOwnerRequest(event, repo) {
  if (!event || typeof event !== 'object' || !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repo)) {
    throw Error('Unsupported repository event')
  }
  const owner = repo.split('/')[0]
  if (event.action !== 'created' || event.repository?.full_name !== repo ||
      event.issue?.number !== 323 || event.comment?.user?.login !== owner) {
    throw Error('Not an owner Issue #323 request')
  }
  const body = event.comment?.body
  const matched = typeof body === 'string' ? REQUEST.exec(body) : null
  if (!matched || matched[0] !== body) throw Error('Expected exact PRP-RELEASE-CHECK sha=<40-lowercase-hex>')
  return matched[1]
}

export function validateHoldSnapshot(raw, exists, symlink = false) {
  if (symlink) throw Error('Invalid release hold symlink')
  if (!exists) return false
  if (typeof raw !== 'string' || raw.length > 4096) throw Error('Invalid release hold contents')
  const hold = JSON.parse(raw)
  if (!hold || typeof hold !== 'object' || Array.isArray(hold) ||
      Object.keys(hold).sort().join(',') !== 'reason,schema_version' ||
      hold.schema_version !== 1 || typeof hold.reason !== 'string' ||
      hold.reason.length < 1 || hold.reason.length > 200) throw Error('Invalid release hold schema')
  return true
}

export function assessGithubPrecheck({requestedSha, checkedOutSha, currentMainSha, hold, ciRuns, ciJobs}) {
  if (![requestedSha, checkedOutSha, currentMainSha].every(sha => typeof sha === 'string' && sha.length === 40 && SHA.test(sha)) ||
      typeof hold !== 'boolean' || !Array.isArray(ciRuns) || !Array.isArray(ciJobs)) {
    throw Error('Invalid precheck inputs')
  }
  const blockers = []
  if (requestedSha !== checkedOutSha || requestedSha !== currentMainSha) {
    blockers.push('STALE_OR_UNMATCHED_MAIN_SHA')
  }
  // Use the most recent exact-SHA main push attempt. An older green run
  // MUST NOT override a later failure for the same candidate.
  const latestMainRun = ciRuns.filter(run =>
    run && Number.isSafeInteger(run.id) && run.id > 0 &&
    run.name === 'CI' && run.event === 'push' &&
    run.head_branch === 'main' && run.head_sha === requestedSha &&
    run.head_repository?.full_name === 'micor-cjj-spec/matrix-prp'
  ).sort((a,b) => b.id - a.id)[0] || null
  const ci = latestMainRun?.status === 'completed' &&
    latestMainRun?.conclusion === 'success' ? latestMainRun : null
  if (!ci) blockers.push('NO_SUCCESSFUL_EXACT_MAIN_PUSH_CI')
  if (ci) {
    if (ciJobs.some(job => !job || typeof job.name !== 'string' || job.name.length > 200)) {
      throw Error('Invalid CI job records')
    }
    if (ciJobs.some(job => job.status !== 'completed' || job.conclusion !== 'success')) {
      blockers.push('CI_JOB_NOT_SUCCESS')
    }
    for (const name of REQUIRED_JOBS) {
      const matches = ciJobs.filter(job => job.name === name)
      if (matches.length !== 1 || matches[0].status !== 'completed' || matches[0].conclusion !== 'success') {
        blockers.push('REQUIRED_JOB_NOT_SUCCESS:' + name)
      }
    }
  }
  if (hold) blockers.unshift('PUBLICATION_HOLD_ACTIVE')
  return {
    schema_version: 1,
    source: 'github_api_and_checked_out_default_branch',
    requested_sha: requestedSha,
    main_sha: currentMainSha,
    workflow_run_id: ci?.id ?? null,
    release_hold: hold,
    state: hold ? 'HELD' : blockers.length ? 'BLOCKED' : 'GITHUB_CI_PRECHECK_PASS_ONLY',
    blockers,
    not_checked: [
      'real_staging_environment', 'module_uat', 'production_backup_restore',
      'production_environment_approval', 'actual_release_artifact_and_controller',
      'production_deployed_sha_and_smoke'
    ],
    production_authorized: false,
    production_live_verified: false,
  }
}

export function summaryMarkdown(r) {
  const lines = [
    '## PRP release precheck (GitHub read-only)', '',
    '**This report is not a deployment approval, deployment record, or production health proof.**', '',
    '| Field | Result |', '| --- | --- |',
    '| State | ' + r.state + ' |',
    '| Requested SHA | `' + r.requested_sha + '` |',
    '| Current main SHA | `' + r.main_sha + '` |',
    '| Exact main push CI run | ' + (r.workflow_run_id ?? 'none') + ' |',
    '| Checked-in release hold | ' + (r.release_hold ? 'ACTIVE' : 'not present') + ' |',
    '| Production authorized | **NO** |',
    '| LIVE verified | **NO** |', '',
    '### Blocking evidence', '',
    ...(!r.blockers.length ? ['- No GitHub-only precheck blocker; production still requires separate approval and verification.'] :
      r.blockers.map(blocker => '- ' + blocker)), '',
    '### Not verified by this workflow', '',
    ...r.not_checked.map(item => '- ' + item), '',
  ]
  return lines.join('\n')
}

async function githubGet(path, token) {
  if (!/^\/repos\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\//.test(path)) throw Error('Unsupported GitHub API path')
  const response = await fetch('https://api.github.com' + path, {
    method: 'GET', redirect: 'error', signal: AbortSignal.timeout(15000),
    headers: {Accept:'application/vnd.github+json',Authorization:'Bearer ' + token,
      'X-GitHub-Api-Version':'2022-11-28', 'User-Agent':'matrix-prp-release-readonly-precheck'}
  })
  if (!response.ok) throw Error('GitHub API precheck unavailable: HTTP ' + response.status)
  return await response.json()
}

const REPO = 'micor-cjj-spec/matrix-prp'
const API = '/repos/' + REPO
const exactSha = v => typeof v === 'string' && v.length === 40 && SHA.test(v)
const positive = v => Number.isSafeInteger(v) && v > 0
const exactRun = (r, sha) => r && r.name === 'CI' &&
  r.path === '.github/workflows/ci.yml' &&
  r.event === 'push' && r.head_branch === 'main' && r.head_sha === sha &&
  r.head_repository?.full_name === REPO

function completeList(response, key) {
  if (!Array.isArray(response?.[key]) || !Number.isInteger(response.total_count) ||
      response.total_count < 0 || response.total_count > 100 ||
      response[key].length !== response.total_count) throw Error('Incomplete GitHub enumeration: ' + key)
  return response[key]
}

function runSignature(r) {
  return [r.id, r.run_attempt, r.status, r.conclusion, r.head_sha,
    r.head_branch, r.event, r.name, r.path, r.head_repository?.full_name]
}

// Only a same-repository main-push snapshot is supported. get is injected
// for synthetic contract tests; the production-facing wrapper uses GET only.
export async function collectGithubSnapshot({requestedSha, checkedOutSha, hold, get}) {
  if (!exactSha(requestedSha) || !exactSha(checkedOutSha) ||
      typeof hold !== 'boolean' || typeof get !== 'function') throw Error('Invalid collection arguments')
  const main = await get(API + '/branches/main')
  const mainSha = main?.commit?.sha
  if (!exactSha(mainSha)) throw Error('Unverifiable main SHA')
  const runsPath = API + '/actions/workflows/ci.yml/runs?branch=main&event=push&head_sha=' +
    requestedSha + '&per_page=100'
  const list = async () => {
    const runs = completeList(await get(runsPath), 'workflow_runs')
    if (runs.some(r => !r || !positive(r.id) || !positive(r.run_attempt)) ||
        new Set(runs.map(r=>r.id)).size !== runs.length) throw Error('Invalid run inventory')
    return runs
  }
  const runs = await list()
  const latest = runs.filter(r => exactRun(r, requestedSha)).sort((a,b)=>b.id-a.id)[0] || null
  let jobs = []
  if (latest?.status === 'completed' && latest.conclusion === 'success') {
    jobs = completeList(await get(API + '/actions/runs/' + latest.id +
      '/attempts/' + latest.run_attempt + '/jobs?per_page=100'), 'jobs')
    if (jobs.some(j => !j || !positive(j.id) || j.run_id !== latest.id ||
        j.run_attempt !== latest.run_attempt || j.head_sha !== requestedSha ||
        j.workflow_name !== 'CI') || new Set(jobs.map(j=>j.id)).size !== jobs.length) {
      throw Error('CI job provenance mismatch')
    }
  }
  if (latest) {
    const current = await get(API + '/actions/runs/' + latest.id)
    if (!current || JSON.stringify(runSignature(current)) !== JSON.stringify(runSignature(latest))) {
      throw Error('CI changed during inspection')
    }
  }
  const after = await list()
  const signature = rr => JSON.stringify(rr.map(runSignature).sort((a,b)=>a[0]-b[0]))
  if (signature(after) !== signature(runs)) throw Error('CI run inventory changed')
  const finalMain = await get(API + '/branches/main')
  if (finalMain?.commit?.sha !== mainSha) throw Error('Main changed during inspection')

  // Preserve the previous diagnostic policy, but pass only eligible CI runs.
  const report = assessGithubPrecheck({
    requestedSha, checkedOutSha, currentMainSha:mainSha, hold,
    ciRuns:runs.filter(r => exactRun(r, requestedSha)), ciJobs:jobs,
  })
  const aligned = requestedSha === checkedOutSha && requestedSha === mainSha
  const allJobsSuccess = Boolean(latest && latest.status === 'completed' &&
    latest.conclusion === 'success' && jobs.length > 0 &&
    jobs.every(j=>j.status==='completed' && j.conclusion==='success') &&
    REQUIRED_JOBS.every(n=>jobs.filter(j=>j.name===n).length===1))
  const bundle = {
    schema_version:1,
    candidate:{repository:REPO,commit:requestedSha,artifact_digest:null,schema:null},
    hold:{state:aligned ? (hold ? 'active' : 'clear') : 'unknown',
      commit:checkedOutSha,ref:'git:' + checkedOutSha + ':publication-hold'},
    evidence:{},
  }
  if (aligned && latest) {
    const status = latest.status !== 'completed' ? 'pending' :
      allJobsSuccess ? 'pass' : latest.conclusion === 'skipped' ? 'skipped' : 'fail'
    bundle.evidence.ci = {
      source:'github_actions',environment:'review',commit:requestedSha,status,
      ref:'github:actions:' + latest.id + ':attempt:' + latest.run_attempt,
      run_id:latest.id,run_attempt:latest.run_attempt,tested_commit:requestedSha,
      all_jobs_success:allJobsSuccess,
    }
  }
  report.snapshot = {
    checked_out_sha:checkedOutSha, current_main_sha:mainSha, aligned,
    latest_run_id:latest?.id ?? null, latest_run_attempt:latest?.run_attempt ?? null,
    latest_run_status:latest?.status ?? null, latest_run_conclusion:latest?.conclusion ?? null,
    enumerated_jobs:jobs.length, successful_jobs:jobs.filter(j=>j.conclusion==='success' && j.status==='completed').length,
    all_jobs_success:allJobsSuccess,
  }
  return {report,bundle}
}

async function collect() {
  if (process.env.GITHUB_EVENT_NAME !== 'issue_comment') throw Error('Unsupported event')
  const repo = process.env.GITHUB_REPOSITORY
  if (repo !== 'micor-cjj-spec/matrix-prp') throw Error('Repository mismatch')
  const event = JSON.parse(readFileSync(process.env.GITHUB_EVENT_PATH, 'utf8'))
  const requestedSha = parseOwnerRequest(event, repo)
  const root = resolve(fileURLToPath(new URL('../..', import.meta.url)))
  const checkedOutSha = execFileSync('git', ['rev-parse','HEAD'], {cwd:root,encoding:'utf8'}).trim()
  if (!SHA.test(checkedOutSha) || checkedOutSha !== process.env.GITHUB_SHA) throw Error('Invalid workflow checkout SHA')
  const holdPath = resolve(root, 'app/deploy/publication-hold.json')
  let holdStat = null
  try { holdStat = lstatSync(holdPath) }
  catch (error) { if (error.code !== 'ENOENT') throw error }
  if (holdStat && (!holdStat.isFile() || holdStat.size > 4096)) throw Error('Invalid release hold file')
  const hold = validateHoldSnapshot(holdStat && !holdStat.isSymbolicLink() ?
    readFileSync(holdPath,'utf8') : null,
    Boolean(holdStat),Boolean(holdStat?.isSymbolicLink()))
  const token = process.env.GITHUB_TOKEN
  if (!token) throw Error('Missing read-only GitHub API token')
  const {report, bundle} = await collectGithubSnapshot({
    requestedSha, checkedOutSha, hold, get: path => githubGet(path, token),
  })
  if (process.env.RUNNER_TEMP) {
    writeFileSync(resolve(process.env.RUNNER_TEMP,'prp-release-evidence-input.json'),
      JSON.stringify(bundle,null,2) + '\n')
  }
  const summary = summaryMarkdown(report)
  if (process.env.GITHUB_STEP_SUMMARY) appendFileSync(process.env.GITHUB_STEP_SUMMARY,summary)
  if (process.env.RUNNER_TEMP) writeFileSync(resolve(process.env.RUNNER_TEMP,'prp-release-precheck.json'),
    JSON.stringify(report,null,2) + '\n')
  process.stdout.write('RELEASE_PRECHECK_STATE=' + report.state + '\n')
  return report
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  collect().catch(error => {
    // Never log raw response, credentials, arbitrary Issue body, or stack traces.
    console.error('PRP_RELEASE_PRECHECK_FAIL_CLOSED:' +
      (error.message.startsWith('GitHub API precheck unavailable: HTTP ') ? 'GITHUB_API_UNAVAILABLE' : 'UNVERIFIED_REQUEST_OR_EVIDENCE'))
    process.exitCode = 1
  })
}
