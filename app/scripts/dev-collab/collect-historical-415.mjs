// Read-only evidence collector for the historical #415 review prototype.
// No Issue inputs, no Git writes, no acceptance authorization.
import {execFileSync} from 'node:child_process'
import {fileURLToPath} from 'node:url'
import {resolve} from 'node:path'
import {verifyHistorical415Evidence} from './review-historical-415.mjs'
const REPO='micor-cjj-spec/matrix-prp'
const ROOT='repos/'+REPO
const HEAD='ba05b6ebe5e435d7cd474bade5accb6fc0c71b65'
const BASE='dc6fc41824e28c49610fba6d9858629ab0b8a34a'
const TEST='d3562e3a64741b4958e078ceb57574a17084a684'
const MERGE='5a30345529a1d07819069822a1b90e07b5376fcc'
const RUNS=[45556141916,45556141762,45556141768]
const JOBS=[139011091923,139011138221,139011091345,139011141150,139011126055,139008538357,139008537901]
const PATHS=['.github/workflows/ci.yml','.github/workflows/feature-impact.yml','.github/workflows/prp-dev-collab-contract.yml']
const read=route=>execFileSync('gh',['api','--method','GET','--hostname','github.com',route],{encoding:'utf8',maxBuffer:4*1024*1024,timeout:30000,stdio:['ignore','pipe','pipe']})
const object=(o,k)=>Object.fromEntries(o.map(x=>[x,k(x)]))
function parse(readText,route){
 const data=readText(route)
 if(typeof data!=='string'||data.length>4*1024*1024)throw new Error('HISTORICAL_API_RESPONSE')
 return JSON.parse(data)
}
// Fixed routes; bounded one-page lists are deliberately rejected rather than
// silently treating a full page as complete. The verifier checks count fields.
export function collectHistorical415(readText=read){
 const get=s=>parse(readText,ROOT+s)
 const integration=()=>get('/branches/integrate%2FREQ-20261031-001')
 const checks=()=>get('/commits/'+HEAD+'/check-runs?per_page=100&filter=latest')
 const e={
   pr:get('/pulls/415'),testCommit:get('/git/commits/'+TEST),mergeCommit:get('/git/commits/'+MERGE),
   integration:integration(),timeline:get('/issues/415/timeline?per_page=100&page=1'),checks:checks(),
   runs:object(RUNS,id=>get('/actions/runs/'+id)),
   jobs:object(RUNS,id=>get('/actions/runs/'+id+'/jobs?per_page=100&filter=latest')),
   logs:object(JOBS,id=>readText(ROOT+'/actions/jobs/'+id+'/logs')),
   workflowBlobs:object(PATHS,p=>[BASE,TEST,MERGE].map(ref=>get('/contents/'+p+'?ref='+ref).sha))
 }
 if(!Array.isArray(e.timeline)||e.timeline.length>=100||
    !Array.isArray(get('/issues/415/timeline?per_page=100&page=2'))||
    get('/issues/415/timeline?per_page=100&page=2').length!==0)throw new Error('HISTORICAL_TIMELINE_INCOMPLETE')
 const result=verifyHistorical415Evidence(e)
 // Re-read critical mutable evidence to catch drift during the read-only check.
 const again={...e,integration:integration(),checks:checks(),
   runs:object(RUNS,id=>get('/actions/runs/'+id)),
   jobs:object(RUNS,id=>get('/actions/runs/'+id+'/jobs?per_page=100&filter=latest'))}
 verifyHistorical415Evidence(again)
 return Object.freeze({...result,mode:'read-only-review',stateWrite:false})
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===resolve(process.argv[1])){
 try{
   if(process.argv.length!==2)throw new Error('HISTORICAL_NO_ARGUMENTS')
   console.log(JSON.stringify(collectHistorical415()))
 }catch(e){
   console.error('Historical review failed: '+(/^HISTORICAL_[A-Z_]+$/.test(e?.message)?e.message:'API_OR_EVIDENCE_ERROR'))
   process.exitCode=1
 }
}
