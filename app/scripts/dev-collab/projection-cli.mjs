#!/usr/bin/env node
import { readFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { basename, dirname } from 'node:path'
import { chooseProjection, renderProjection } from './projection.mjs'
import { validateSnapshot } from './core.mjs'

const REQ=/^REQ-[0-9]{8}-[0-9]{3}$/
const SHA=/^[a-f0-9]{40}$/
function gh(...args) {
  return execFileSync('gh',['api',...args],{encoding:'utf8',maxBuffer:1024*1024})
}
function run() {
  if (process.argv.length!==4) throw new Error('EXPECTED_STATE_AND_SHA')
  if (process.env.GITHUB_REPOSITORY!=='micor-cjj-spec/matrix-prp') throw new Error('WRONG_REPOSITORY')
  if (process.env.GITHUB_ACTOR!==process.env.GITHUB_REPOSITORY_OWNER) throw new Error('OWNER_ONLY')
  if (!process.env.GH_TOKEN) throw new Error('MISSING_GH_TOKEN')
  const [statePath,sha]=process.argv.slice(2)
  const id=basename(statePath).replace(/\.json$/,'')
  if (!REQ.test(id)||!SHA.test(sha)) throw new Error('INVALID_STATE_IDENTIFIER')
  const snapshot=JSON.parse(readFileSync(statePath,'utf8'))
  validateSnapshot(snapshot)
  if (snapshot.requirement_id!==id) throw new Error('REQUIREMENT_MISMATCH')
  const issue=JSON.parse(gh(`repos/${process.env.GITHUB_REPOSITORY}/issues/${snapshot.issue_number}`))
  if (issue.pull_request||typeof issue.title!=='string'||!issue.title.startsWith(`[REQ][${id}]`)) {
    throw new Error('ISSUE_MISMATCH')
  }
  const endpoint=`repos/${process.env.GITHUB_REPOSITORY}/issues/${snapshot.issue_number}/comments`
  const pages=JSON.parse(gh('--paginate','--slurp',endpoint+'?per_page=100'))
  if (!Array.isArray(pages)||!pages.every(Array.isArray)) throw new Error('UNEXPECTED_COMMENT_PAGES')
  const body=renderProjection(snapshot,sha)
  const action=chooseProjection(pages.flat(),id,snapshot.version,body)
  // Ref may advance while reading API: stop rather than writing a known-stale projection.
  const current=execFileSync('git',['ls-remote','origin','refs/heads/prp-collab-state'],
    {encoding:'utf8',maxBuffer:4096}).trim().split(/\s+/)[0]
  if (current!==sha) throw new Error('STATE_REF_ADVANCED')
  if(action.action==='unchanged'){
    console.log('PRP_ISSUE_PROJECTION_UNCHANGED=YES')
    return
  }
  const args=action.action==='create'
    ?['-X','POST',endpoint]
    :['-X','PATCH',`repos/${process.env.GITHUB_REPOSITORY}/issues/comments/${action.id}`]
  gh(...args,'-f','body='+body,'--silent')
  console.log('PRP_ISSUE_PROJECTION_'+action.action.toUpperCase()+'=YES')
}
try{run()}catch(err){
  console.error('PRP_ISSUE_PROJECTION_ERROR='+String(err?.message||'FAILED').slice(0,180))
  process.exitCode=1
}
