import {readFileSync,writeFileSync,mkdtempSync} from 'node:fs'
import {join} from 'node:path'
import {tmpdir} from 'node:os'
import {execFileSync} from 'node:child_process'
import {verifyMigrationEvidence} from './migration-guard.mjs'
import {CollabError} from './core.mjs'

const REPO='micor-cjj-spec/matrix-prp'
const BASE='062036f7021e215ffbfdcbf5689d207a0549b68b'
const PROPOSAL='fb57656dca6df5f12e083fc0430263b4d88e452d'
const REF='refs/heads/prp-collab-state'
const PROP_REF='refs/heads/proposal/prp-collab-state-scope-20261101'
const FILE='requirements/REQ-20261031-001.json'
const check=(v,code)=>{if(!v)throw new CollabError(code)}
const run=(p,args,options={})=>execFileSync(p,args,{
 encoding:'utf8',timeout:15000,maxBuffer:4*1024*1024,...options}).trim()
const git=(...a)=>run('git',a)
const gh=(p,token)=>JSON.parse(run('gh',['api',p],token?{
 env:{...process.env,GH_TOKEN:token}}:{}))

export function authorizeOwnerIssuedMigration(validated,stateSha,proposalSha){
 check(validated.oneShotMigration===true&&
   validated.actor==='micor-cjj-spec'&&
   validated.command?.type==='migrate_v1'&&
   validated.command.requirement_id==='REQ-20261031-001'&&
   validated.command.expected_state_sha===BASE&&
   validated.command.expected_proposal_sha===PROPOSAL&&
   stateSha===BASE&&proposalSha===PROPOSAL,'MIGRATION_ISSUE_NOT_APPROVED')
 return true
}

/** Invoked only after strict GitHub-owned issues.opened event validation. */
export function applyOwnerIssuedMigration(validated,env){
 const getRemote=(ref)=>{
   const line=git('ls-remote','--exit-code','--refs','origin',ref)
   const pair=line.split('\t')
   check(pair.length===2&&pair[1]===ref,'MIGRATION_REMOTE_REF_INVALID')
   return pair[0]
 }
 const current=getRemote(REF),candidate=getRemote(PROP_REF)
 authorizeOwnerIssuedMigration(validated,current,candidate)
 check(env.GITHUB_SHA===getRemote('refs/heads/main'),'MIGRATION_MAIN_MOVED')
 git('fetch','--no-tags','origin',REF)
 check(git('rev-parse','FETCH_HEAD')===BASE,'MIGRATION_STATE_CHANGED')
 git('fetch','--no-tags','origin',PROP_REF)
 check(git('rev-parse','FETCH_HEAD')===PROPOSAL,'MIGRATION_PROPOSAL_CHANGED')
 git('merge-base','--is-ancestor',BASE,PROPOSAL)
 check(git('diff','--name-only',BASE,PROPOSAL)===FILE,'MIGRATION_CHANGED_EXTRA_FILES')
 const temp=mkdtempSync(join(env.RUNNER_TEMP||tmpdir(),'prp-owner-migrate-'))
 const before=JSON.parse(git('show',BASE+':'+FILE))
 const after=JSON.parse(git('show',PROPOSAL+':'+FILE))
 const pr=gh('repos/'+REPO+'/pulls/144')
 const prFiles=gh('repos/'+REPO+'/pulls/144/files?per_page=100')
 const ruleset=gh('repos/'+REPO+'/rulesets/'+env.COLLAB_RULESET_ID)
 // The explicit owner-created Issue replaces a GUI approval, NOT any data-scope checks.
 verifyMigrationEvidence({before,after,pr,prFiles,rule:ruleset,
   appId:Number(env.COLLAB_APP_ID),ruleId:Number(env.COLLAB_RULESET_ID),
   stateSha:BASE,proposalSha:PROPOSAL,mode:'verify',
   approvalPhrase:'',appInstallation:null})
 check(typeof env.COLLAB_APP_TOKEN==='string'&&env.COLLAB_APP_TOKEN.length>0,
   'MIGRATION_APP_TOKEN_MISSING')
 const repos=gh('installation/repositories',env.COLLAB_APP_TOKEN)
 check(repos?.total_count===1&&repos?.repositories?.length===1&&
   repos.repositories[0].full_name===REPO,'MIGRATION_APP_SCOPE')
 check(getRemote(REF)===BASE&&getRemote(PROP_REF)===PROPOSAL&&
   getRemote('refs/heads/main')===env.GITHUB_SHA,'MIGRATION_CHANGED_BEFORE_PUSH')
 git('worktree','add','--detach',temp,BASE)
 writeFileSync(join(temp,FILE),JSON.stringify(after,null,2)+'\n',{mode:0o600})
 git('-C',temp,'add','--',FILE)
 check(git('-C',temp,'diff','--cached','--name-only')===FILE,'MIGRATION_STAGED_SCOPE')
 git('-C',temp,'diff','--cached','--check')
 git('-C',temp,'config','user.name','prp-collab-writer[bot]')
 git('-C',temp,'config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
 git('-C',temp,'commit','-m','chore(collab): owner-issued V0 to V1 migration',
   '-m','Request-issue: '+validated.source_issue,
   '-m','Request-id: '+validated.command.request_id,
   '-m','Pinned-proposal: '+PROPOSAL)
 check(getRemote(REF)===BASE&&getRemote('refs/heads/main')===env.GITHUB_SHA,
   'MIGRATION_FINAL_RACE')
 git('-C',temp,'push','origin','HEAD:'+REF)
 const newSha=git('-C',temp,'rev-parse','HEAD')
 check(getRemote(REF)===newSha,'MIGRATION_POST_PUSH_SHA')
 return {state_sha:newSha,version:1,requirement_id:'REQ-20261031-001',
   request_id:validated.command.request_id,source_issue:validated.source_issue}
}
