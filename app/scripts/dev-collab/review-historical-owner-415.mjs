// Review candidate only: single historical recovery, never a generic fallback.
import {CollabError,validateSnapshot} from './core.mjs'
import {verifyTaskEvidence,REQUIRED_CHECKS} from './review-gate.mjs'
import {collectHistorical415} from './collect-historical-415.mjs'
const R='micor-cjj-spec/matrix-prp',HEAD='ba05b6ebe5e435d7cd474bade5accb6fc0c71b65',STATE='701cd06ba1358b8f09e337296db9f7b9b66a71d9',MERGE='5a30345529a1d07819069822a1b90e07b5376fcc',TARGET='integrate/REQ-20261031-001'
const check=(ok,code)=>{if(!ok)throw new CollabError(code)}
const equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b)
export function verifyHistorical415Binding(s,v,stateSha,env){
 validateSnapshot(s)
 const c=v.command,t=s.tasks.find(t=>t.task_id==='T-001')
 check(env.GITHUB_ACTIONS==='true'&&env.GITHUB_REF==='refs/heads/main'&&env.GITHUB_REPOSITORY===R&&env.GITHUB_EVENT_NAME==='issues'&&env.GITHUB_EVENT_ACTION==='opened'&&env.GITHUB_ACTOR==='micor-cjj-spec'&&env.GITHUB_REPOSITORY_OWNER==='micor-cjj-spec'&&env.GITHUB_WORKFLOW_REF===R+'/.github/workflows/prp-collab-issue-ingress.yml@refs/heads/main'&&/^[a-f0-9]{40}$/.test(env.GITHUB_SHA||'')&&typeof env.GH_TOKEN==='string'&&env.GH_TOKEN.length>0,'HISTORICAL_OWNER_CONTEXT')
 check(v.historical415===true&&v.actor==='micor-cjj-spec'&&v.actorId===123868412&&v.expected_version===13&&v.expectedStateSha===STATE&&stateSha===STATE&&s.version===13&&s.status==='ACTIVE'&&s.requirement_id==='REQ-20261031-001'&&c.type==='accept'&&c.requirement_id===s.requirement_id&&c.task_id==='T-001'&&c.note==='historical-415-approved-recovery-v1'&&c.pr_number===415&&c.head_sha===HEAD&&c.worker_id==='chat_t001_delivery_20261125'&&t?.status==='IN_REVIEW'&&t.pr_number===415&&t.head_sha===HEAD&&t.claim?.actor===v.actor&&t.claim?.worker_id===c.worker_id&&t.claim?.claim_id===c.claim_id,'HISTORICAL_OWNER_BINDING')
 const last=s.processed_requests.filter(x=>x.receipt.task_id==='T-001').at(-1)
 check(last?.request_id==='ebd25c98-0723-4637-9e76-d2baf7b90b28'&&last.actor===v.actor&&last.receipt.type==='submit'&&last.receipt.version===13&&last.receipt.status==='IN_REVIEW','HISTORICAL_SUBMIT_BINDING')
 return true
}
export function verifyHistoricalIntegrationPolicy(rule){
 const rules=rule?.rules??[],p=rules.find(x=>x.type==='pull_request')?.parameters,c=rules.find(x=>x.type==='required_status_checks')?.parameters
 check(rule?.id===28050327&&rule.enforcement==='active'&&rule.target==='branch'&&equal(rule.conditions?.ref_name?.include,['refs/heads/'+TARGET])&&equal(rule.conditions?.ref_name?.exclude,[])&&equal(rule.bypass_actors,[])&&rules.some(x=>x.type==='deletion')&&rules.some(x=>x.type==='non_fast_forward')&&equal(p?.allowed_merge_methods,['merge'])&&p.required_review_thread_resolution===true&&c?.strict_required_status_checks_policy===true&&equal(c.required_status_checks?.map(x=>x.context).sort(),REQUIRED_CHECKS.slice().sort())&&c.required_status_checks.every(x=>x.integration_id===15368),'HISTORICAL_INTEGRATION_POLICY')
 return true
}
export function trustedHistorical415Context(s,v,stateSha,env,api,collect=collectHistorical415){
 verifyHistorical415Binding(s,v,stateSha,env)
 const root='repos/'+R
 verifyHistoricalIntegrationPolicy(api(root+'/rulesets/28050327'))
 const pr=api(root+'/pulls/415'),branch=api(root+'/branches/'+encodeURIComponent(TARGET))
 check(pr?.base?.repo?.id===1261866723&&pr?.head?.repo?.id===1261866723&&pr.merge_commit_sha===MERGE&&branch?.commit?.sha===MERGE,'HISTORICAL_LIVE_PR_BINDING')
 const comparison=api(root+'/compare/'+MERGE+'...'+MERGE),checks=api(root+'/commits/'+HEAD+'/check-runs?per_page=100'),files=api(root+'/pulls/415/files?per_page=100')
 verifyTaskEvidence(s,'T-001',{pr,branch,comparison,checks,files})
 const result=collect()
 check(result?.historicalEvidenceVerified===true&&result.pr===415&&result.head===HEAD&&result.merge===MERGE&&result.syntheticMerge==='d3562e3a64741b4958e078ceb57574a17084a684'&&result.checks===7&&result.mode==='read-only-review'&&result.stateWrite===false,'HISTORICAL_OWNER_EVIDENCE')
 verifyHistoricalIntegrationPolicy(api(root+'/rulesets/28050327'))
 return Object.freeze({reviewerAuthorized:true,ciVerified:true,mergedIntoIntegration:true,historical415Verified:true})
}
