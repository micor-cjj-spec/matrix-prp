// OFFLINE REVIEW CONTRACT ONLY. No GitHub API, credentials, push or state writer.
// The caller must independently obtain current protected-state and GitHub evidence.
import {createHash} from 'node:crypto'
import {CollabError} from './core.mjs'
import {capturePremergeReceipt} from './review-receipt.mjs'
const SHA=/^[a-f0-9]{40}$/,REQ=/^REQ-[0-9]{8}-[0-9]{3}$/,TASK=/^T-[0-9]{3}$/,UUID=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i
const check=(ok,code)=>{if(!ok)throw new CollabError(code)}
const canon=v=>Array.isArray(v)?'['+v.map(canon).join(',')+']':v!==null&&typeof v==='object'?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canon(v[k])).join(',')+'}':JSON.stringify(v)
const digest=b=>createHash('sha256').update(canon(b)).digest('hex')
const stable=b=>{const {captured_at,state_sha,state_version,...rest}=b;return rest}
export function receiptPath(b){
 check(REQ.test(b?.requirement_id)&&TASK.test(b?.task_id)&&UUID.test(b?.submit_request_id),'STORE_PATH_INVALID')
 return 'receipts/'+b.requirement_id+'/'+b.task_id+'/'+b.submit_request_id.toLowerCase()+'.json'
}
export function parseStoredReceipt(bytes){
 check(typeof bytes==='string'&&Buffer.byteLength(bytes)<=65536,'STORE_BYTES_INVALID')
 let v
 try{v=JSON.parse(bytes)}catch{throw new CollabError('STORE_JSON_INVALID')}
 check(v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).sort().join(',')==='body,digest'&&
  v.body?.schema_version===1&&v.digest===digest(v.body),'STORE_DIGEST_INVALID')
 check(bytes===JSON.stringify(v,null,2)+'\n','STORE_NONCANONICAL')
 receiptPath(v.body)
 return v
}
// existingBytes must be read from the exact expected protected-state commit.
// No externally provided receipt is accepted for a new write.
export function planReceiptAppend({snapshot,taskId,evidence,capturedAt,expectedStateSha,observedStateSha,existingBytes=null}){
 check(SHA.test(expectedStateSha)&&observedStateSha===expectedStateSha,'STORE_STALE_STATE')
 const next=capturePremergeReceipt(snapshot,taskId,evidence,{stateSha:observedStateSha,capturedAt})
 const path=receiptPath(next.body)
 if(existingBytes!==null){
   const old=parseStoredReceipt(existingBytes)
   check(receiptPath(old.body)===path&&SHA.test(old.body.state_sha)&&
     Number.isSafeInteger(old.body.state_version)&&old.body.state_version>=old.body.submit_version&&
     old.body.state_version<=snapshot.version&&Number.isFinite(Date.parse(old.body.captured_at))&&
     Date.parse(old.body.captured_at)<=Date.parse(capturedAt),'STORE_EXISTING_CONTEXT')
   // Re-run capture against current premerge evidence with the original timestamp,
   // then require the same semantic payload. No overwrite, including rerun changes.
   const original=capturePremergeReceipt(snapshot,taskId,evidence,{stateSha:old.body.state_sha,capturedAt:old.body.captured_at})
   check(canon(stable(old.body))===canon(stable(original.body))&&canon(stable(old.body))===canon(stable(next.body)),'STORE_IMMUTABLE_CONFLICT')
   return Object.freeze({action:'replay',path,expectedStateSha,digest:old.digest,bytes:existingBytes})
 }
 const bytes=JSON.stringify(next,null,2)+'\n'
 check(Buffer.byteLength(bytes)<=65536,'STORE_BYTES_INVALID')
 return Object.freeze({action:'append',path,expectedStateSha,digest:next.digest,bytes})
}
// Verify the intended single-file commit envelope before a future writer pushes.
// Compare metadata comes from Git, not from a worker or Issue body.
export function verifyReceiptAppendCommit(plan,{commit,parent,files,committedBytes,remoteBefore}){
 check(plan?.action==='append'&&SHA.test(plan.expectedStateSha)&&remoteBefore===plan.expectedStateSha,'STORE_STALE_STATE')
 check(SHA.test(commit?.sha)&&commit.sha!==plan.expectedStateSha&&
   canon(commit.parents?.map(p=>p.sha))===canon([plan.expectedStateSha])&&parent===plan.expectedStateSha,'STORE_COMMIT_PARENT')
 check(Array.isArray(files)&&files.length===1&&files[0].filename===plan.path&&files[0].status==='added','STORE_WRITE_SCOPE')
 const v=parseStoredReceipt(committedBytes)
 check(receiptPath(v.body)===plan.path&&v.body.state_sha===plan.expectedStateSha&&
   v.digest===plan.digest&&committedBytes===plan.bytes,'STORE_COMMIT_CONTENT')
 return Object.freeze({appendEnvelopeVerified:true,commit_sha:commit.sha,path:plan.path,digest:plan.digest})
}
