import { readFileSync } from 'node:fs'
import { CollabError } from './core.mjs'

const REF='refs/heads/prp-collab-state'
const MANDATORY=new Set(['update','deletion','non_fast_forward'])
function check(ok,code){if(!ok)throw new CollabError(code)}

export function verifyStateBranchRuleset(rule,appId){
  check(Number.isSafeInteger(appId) && appId>0,'CONFIGURE_DEDICATED_APP')
  check(rule?.target==='branch' && rule?.enforcement==='active','RULESET_NOT_ACTIVE')
  const refs=rule?.conditions?.ref_name
  check(Array.isArray(refs?.include) && refs.include.length===1 && refs.include[0]===REF &&
    Array.isArray(refs.exclude) && refs.exclude.length===0,'RULESET_TARGET_NOT_EXACT')
  const types=new Set((rule.rules??[]).map(x=>x?.type))
  check([...MANDATORY].every(t=>types.has(t)),'MISSING_REQUIRED_STATE_RULES')
  const bypass=rule.bypass_actors
  check(Array.isArray(bypass) && bypass.length===1 &&
    bypass[0].actor_type==='Integration' && bypass[0].actor_id===appId &&
    bypass[0].bypass_mode==='always','UNSAFE_RULESET_BYPASS')
  return Object.freeze({allowed:true,rule_id:rule.id,app_id:appId,ref:REF})
}

if(process.argv[1] && process.argv[1].endsWith('/state-rule-policy.mjs')){
  try{
    if(process.argv.length!==3)throw new CollabError('RULESET_PATH_REQUIRED')
    const appId=Number(process.env.COLLAB_APP_ID)
    const rule=JSON.parse(readFileSync(process.argv[2],'utf8'))
    verifyStateBranchRuleset(rule,appId)
    console.log('PRP_COLLAB_RULESET_VALID=YES')
  }catch(err){
    console.error('PRP_COLLAB_RULESET_ERROR='+(err?.code||'INVALID_RULESET'))
    process.exitCode=1
  }
}
