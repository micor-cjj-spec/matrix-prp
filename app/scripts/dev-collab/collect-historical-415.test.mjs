import test from 'node:test'
import assert from 'node:assert/strict'
import {collectHistorical415,readHistoricalJobLog,historicalLogRoute} from './collect-historical-415.mjs'
test('collector has a fixed GET-only route set and fails closed on absent API data',()=>{
 const seen=[]
 assert.throws(()=>collectHistorical415(route=>{seen.push(route);throw new Error('not available')}),/not available/)
 assert.deepEqual(seen,['repos/micor-cjj-spec/matrix-prp/pulls/415'])
})
test('malformed API response is rejected before collecting further evidence',()=>{
 const seen=[]
 assert.throws(()=>collectHistorical415(route=>{seen.push(route);return '<html>bad gateway</html>'}),SyntaxError)
 assert.equal(seen.length,1)
})
test('oversized response is rejected before processing',()=>{
 assert.throws(()=>collectHistorical415(()=> 'x'.repeat(4*1024*1024+1)),/HISTORICAL_API_RESPONSE/)
})

const route='repos/micor-cjj-spec/matrix-prp/actions/jobs/139011091923/logs'
test('historical log route is limited to the seven fixed job identities',()=>{
 assert.equal(historicalLogRoute(route),true)
 for(const v of [route+'?x=1',route.replace('139011091923','1'),route.replace('matrix-prp','other'),'https://evil.example/'])assert.equal(historicalLogRoute(v),false)
})
test('redirect download never transmits GitHub authorization to storage',async()=>{
 const calls=[],fetcher=async(url,opts)=>{calls.push({url:String(url),opts});return calls.length===1?new Response(null,{status:302,headers:{location:'https://example.blob.core.windows.net/log?sig=synthetic'}}):new Response('historical log')}
 assert.equal(await readHistoricalJobLog(route,{token:'synthetic',fetcher}),'historical log')
 assert.equal(calls[0].opts.headers.Authorization,'Bearer synthetic')
 assert.equal(calls[1].opts.headers,undefined)
 assert.equal(calls[1].opts.redirect,'manual')
})
test('unsafe redirect, second redirect, invalid route and oversized logs fail closed',async()=>{
 for(const location of ['http://example.blob.core.windows.net/log','https://evil.example/log','https://example.blob.core.windows.net.evil.example/log','https://user@example.blob.core.windows.net/log','https://example.blob.core.windows.net:8443/log']){
  let calls=0
  await assert.rejects(readHistoricalJobLog(route,{token:'synthetic',fetcher:async()=>{calls++;return new Response(null,{status:302,headers:{location}})}}),/HISTORICAL_LOG_REDIRECT/)
  assert.equal(calls,1)
 }
 await assert.rejects(readHistoricalJobLog(route,{token:'synthetic',fetcher:async()=>new Response(null,{status:302,headers:{location:'https://example.blob.core.windows.net/log'}})}),/HISTORICAL_LOG_HTTP/)
 await assert.rejects(readHistoricalJobLog(route.replace('139011091923','2'),{token:'synthetic',fetcher:async()=>{throw Error('not called')}}),/HISTORICAL_LOG_REQUEST/)
 await assert.rejects(readHistoricalJobLog(route,{token:'synthetic',fetcher:async()=>new Response('x'.repeat(4*1024*1024+1))}),/HISTORICAL_LOG_SIZE/)
})
