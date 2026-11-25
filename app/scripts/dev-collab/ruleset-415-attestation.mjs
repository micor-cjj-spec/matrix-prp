// Single-use historical #415 governance contract; review-only until separately activated.
import {createHash} from 'node:crypto'
import {CollabError} from './core.mjs'
const check=(ok,code)=>{if(!ok)throw new CollabError(code)}
const canon=v=>Array.isArray(v)?'['+v.map(canon).join(',')+']':v!==null&&typeof v==='object'?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canon(v[k])).join(',')+'}':JSON.stringify(v)
const digest=v=>createHash('sha256').update(canon(v)).digest('hex')
const iso=v=>{check(typeof v==='string'&&Number.isFinite(Date.parse(v)),'HISTORICAL_RULESET_TIME');return new Date(v).toISOString()}
const SHA=/^[a-f0-9]{40}$/
const SNAPSHOT={
  "id": 28050327,
  "name": "protect-collab-integration",
  "target": "branch",
  "source_type": "Repository",
  "source": "micor-cjj-spec/matrix-prp",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "exclude": [],
      "include": [
        "refs/heads/integrate/REQ-20261031-001"
      ]
    }
  },
  "rules": [
    {
      "type": "deletion"
    },
    {
      "type": "non_fast_forward"
    },
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": true,
        "required_reviewers": [],
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": true,
        "require_extra_approval_for_unattributed_changes": false,
        "allowed_merge_methods": [
          "merge"
        ]
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "do_not_enforce_on_create": true,
        "required_status_checks": [
          {
            "context": "backend-tests",
            "integration_id": 15368
          },
          {
            "context": "web-build",
            "integration_id": 15368
          },
          {
            "context": "mobile-build",
            "integration_id": 15368
          },
          {
            "context": "db-migration-integration",
            "integration_id": 15368
          },
          {
            "context": "video-db-integration",
            "integration_id": 15368
          },
          {
            "context": "impact-report",
            "integration_id": 15368
          },
          {
            "context": "dev-collab-contract",
            "integration_id": 15368
          }
        ]
      }
    }
  ],
  "node_id": "RRS_lACqUmVwb3NpdG9yec5LNo7jzgGsA5c",
  "created_at": "2026-11-25T05:47:06.929Z",
  "updated_at": "2026-11-25T05:47:07.076Z",
  "bypass_actors": []
}
const KEYS=Object.keys(SNAPSHOT).filter(k=>k!=='bypass_actors')
const PREFIX='historical-415-approved-recovery-v2:'
const MERGE='5a30345529a1d07819069822a1b90e07b5376fcc'
export const OWNER_RULESET_DIGEST=digest(SNAPSHOT)
export const OWNER_RULESET_REVISION=SNAPSHOT.updated_at
export const historicalNote=attestation=>PREFIX+digest(attestation)
export const isHistoricalNote=note=>typeof note==='string'&&note.startsWith('historical-415-approved-recovery-')
export function validateOwnerAttestation(a,{requestId,mainSha,issueCreatedAt,now=Date.now()}){
 const keys=['schema_version','request_id','snapshot_sha256','rule_updated_at','observed_at','expected_main_sha','merge_sha']
 check(a&&typeof a==='object'&&!Array.isArray(a)&&Object.keys(a).length===keys.length&&keys.every(k=>Object.hasOwn(a,k))&&
  a.schema_version===1&&a.request_id===requestId&&a.snapshot_sha256===OWNER_RULESET_DIGEST&&
  a.rule_updated_at===OWNER_RULESET_REVISION&&SHA.test(mainSha)&&a.expected_main_sha===mainSha&&a.merge_sha===MERGE,'HISTORICAL_ATTESTATION_BINDING')
 const observed=Date.parse(iso(a.observed_at)),created=Date.parse(iso(issueCreatedAt))
 // Owner's separate live full-list read must precede issue creation within 5 minutes;
 // tolerate 30s clock skew only for server time rounding. No queue-time extension.
 check(observed<=created+30000&&created-observed<=300000&&now>=created-30000&&now-observed<=600000&&now>=observed-30000,'HISTORICAL_ATTESTATION_EXPIRED')
 return true
}
export function verifyOwnerAttestedPolicy(rule){
 check(rule&&typeof rule==='object'&&rule.current_user_can_bypass==='never','HISTORICAL_RULESET_CALLER')
 const visible={}
 for(const k of KEYS){
  check(Object.hasOwn(rule,k),'HISTORICAL_RULESET_FIELD_MISSING')
  visible[k]=k==='created_at'||k==='updated_at'?iso(rule[k]):rule[k]
 }
 // Reject unknown policy fields rather than ignoring a changed response shape.
 check(Object.keys(rule).every(k=>KEYS.includes(k)||['bypass_actors','current_user_can_bypass','_links'].includes(k)),'HISTORICAL_RULESET_UNKNOWN_FIELD')
 const expected=Object.fromEntries(KEYS.map(k=>[k,SNAPSHOT[k]]))
 check(canon(visible)===canon(expected),'HISTORICAL_RULESET_SNAPSHOT_DRIFT')
 // Missing list is NOT an empty list. Only the authenticated one-shot owner
 // attestation may bridge this explicitly approved visibility gap.
 if(Object.hasOwn(rule,'bypass_actors'))check(Array.isArray(rule.bypass_actors)&&rule.bypass_actors.length===0,'HISTORICAL_RULESET_BYPASS')
 return Object.freeze({visiblePolicyVerified:true,bypassListVisible:Object.hasOwn(rule,'bypass_actors'),snapshotDigest:OWNER_RULESET_DIGEST,revision:OWNER_RULESET_REVISION})
}
