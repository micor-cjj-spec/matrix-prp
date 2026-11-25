import test from 'node:test'
import assert from 'node:assert/strict'
import {collectHistorical415} from './collect-historical-415.mjs'
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
