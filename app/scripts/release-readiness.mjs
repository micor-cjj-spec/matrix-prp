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
    headers: {Accept:'application/vnd.github+json',Authorization:'Bearer ' + token,
      'X-GitHub-Api-Version':'2022-11-28', 'User-Agent':'matrix-prp-release-readonly-precheck'}
  })
  if (!response.ok) throw Error('GitHub API precheck unavailable: HTTP ' + response.status)
  return await response.json()
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
  const main = await githubGet('/repos/' + repo + '/branches/main', token)
  const mainSha = main?.commit?.sha
  if (!SHA.test(mainSha)) throw Error('Unverifiable current main SHA')
  // Never trust a successful CI from a previous main commit or a pull_request event.
  const runsResponse = await githubGet('/repos/' + repo +
    '/actions/workflows/ci.yml/runs?branch=main&event=push&head_sha=' + requestedSha +
    '&per_page=100',token)
  if (!Array.isArray(runsResponse?.workflow_runs) ||
      !Number.isInteger(runsResponse.total_count) || runsResponse.total_count > 100 ||
      runsResponse.workflow_runs.length !== runsResponse.total_count) throw Error('Incomplete CI run enumeration')
  const ciRuns = runsResponse.workflow_runs
  const latest = ciRuns.filter(run =>
    run?.name === 'CI' && run?.event === 'push' && run?.head_sha === requestedSha &&
    run?.head_branch === 'main' &&
    run?.head_repository?.full_name === repo).sort((a,b) => b.id - a.id)[0]
  const exact = latest?.status === 'completed' && latest?.conclusion === 'success' ? latest : null
  let ciJobs = []
  if (exact) {
    if (!Number.isSafeInteger(exact.run_attempt) || exact.run_attempt < 1) throw Error('Invalid CI run attempt')
    const response = await githubGet('/repos/' + repo +
      '/actions/runs/' + exact.id + '/attempts/' + exact.run_attempt + '/jobs?per_page=100',token)
    if (!Array.isArray(response?.jobs) || !Number.isInteger(response.total_count) ||
        response.total_count > 100 || response.jobs.length !== response.total_count) {
      throw Error('Incomplete CI job enumeration: fail closed')
    }
    ciJobs = response.jobs
    if (ciJobs.some(job => job.run_id !== exact.id || job.run_attempt !== exact.run_attempt)) throw Error('CI job provenance mismatch')
    const current = await githubGet('/repos/' + repo + '/actions/runs/' + exact.id, token)
    if (current.run_attempt !== exact.run_attempt || current.status !== 'completed' ||
        current.conclusion !== 'success' || current.head_sha !== requestedSha) throw Error('CI changed during inspection')
  }
  // Re-read both main and the exact-SHA run list after collecting jobs.
  const latestMain = await githubGet('/repos/' + repo + '/branches/main', token)
  if (latestMain?.commit?.sha !== mainSha) throw Error('Main changed during inspection')
  const latestRuns = await githubGet('/repos/' + repo +
    '/actions/workflows/ci.yml/runs?branch=main&event=push&head_sha=' + requestedSha +
    '&per_page=100',token)
  const signature = runs => JSON.stringify(runs.map(x => [x.id,x.run_attempt,x.status,x.conclusion]).sort((a,b)=>a[0]-b[0]))
  if (!Array.isArray(latestRuns?.workflow_runs) || latestRuns.total_count !== runsResponse.total_count ||
      signature(latestRuns.workflow_runs) !== signature(ciRuns)) throw Error('CI runs changed during inspection')
  const report = assessGithubPrecheck({
    requestedSha, checkedOutSha, currentMainSha:mainSha,
    hold, ciRuns, ciJobs,
  })
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
