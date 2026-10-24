// Fixed targets, no credentials, no raw response or sensitive logs.
const h2=require('node:http2'),tls=require('node:tls'),crypto=require('node:crypto');
function safeSemantic(b){let semantic={};try{const d=JSON.parse(b.toString());if(d.data&&typeof d.data.status==='string')semantic.health=['UP','DOWN','UNKNOWN'].includes(d.data.status)?d.data.status:'UNEXPECTED_VALUE';}catch{}return semantic;}
function safeError(stage,e){
 const codes=new Set(['ECONNREFUSED','ECONNRESET','ECONNABORTED','ETIMEDOUT','EHOSTUNREACH','ENETUNREACH','EPIPE','ERR_TLS_CERT_ALTNAME_INVALID','CERT_HAS_EXPIRED','DEPTH_ZERO_SELF_SIGNED_CERT','UNABLE_TO_VERIFY_LEAF_SIGNATURE','ERR_HTTP2_ERROR','ERR_HTTP2_STREAM_ERROR','ERR_HTTP2_SESSION_ERROR']);
 const stages=new Set(['TCP','TLS','H2_SESSION','HEADERS','BODY']);
 return {stage:stages.has(stage)?stage:'UNKNOWN',exception_type:e instanceof Error?'Error':'UNKNOWN',code:e&&codes.has(e.code)?e.code:null,errno:e&&Number.isInteger(e.errno)?e.errno:null};
}
module.exports={safeSemantic,safeError};
if(require.main===module){
let input='';process.stdin.on('data',b=>{input+=b;if(input.length>4096)process.exit(2)});
process.stdin.on('end',()=>{
 const p=JSON.parse(input);if(!['207.57.123.94','2001:df1:7880:6::63','127.0.0.1','::1'].includes(p.ip)||![443,19443].includes(p.port)||!['micor.top','www.micor.top'].includes(p.sni)||p.path!='/prp/api/health')process.exit(2);
 let client,req,done=false,total=0,chunks=[],status=null,alpn=null,verified=false,stage='TCP';
 function finish(error,cause){if(done)return;done=true;clearTimeout(timer);const b=Buffer.concat(chunks);const semantic=safeSemantic(b);process.stdout.write(JSON.stringify({status,error:error||null,error_detail:error?safeError(stage,cause):null,alpn,protocol:'2',chain_verified:verified,san_verified:verified,body_sha256:crypto.createHash('sha256').update(b).digest('hex'),body_bytes:b.length,semantic}));if(req)req.close();if(client)client.destroy();}
 const timer=setTimeout(()=>finish('TIMEOUT'),10000);
 client=h2.connect('https://'+p.sni,{createConnection:()=>{const socket=tls.connect({host:p.ip,port:p.port,servername:p.sni,ALPNProtocols:['h2'],rejectUnauthorized:true});socket.once('connect',()=>{stage='TLS'});socket.once('secureConnect',()=>{stage='H2_SESSION'});socket.once('error',e=>finish('H2_TLS_OR_TRANSPORT_ERROR',e));return socket;}});
 client.on('error',e=>finish('H2_SESSION_ERROR',e));client.on('connect',()=>{alpn=client.socket.alpnProtocol;verified=client.socket.authorized===true;const headers={':method':'GET',':scheme':'https',':authority':p.authority,':path':p.path};if(p.host!==null)headers.host=p.host;stage='HEADERS';req=client.request(headers);req.on('response',h=>{status=Number(h[':status']);stage='BODY'});req.on('data',b=>{total+=b.length;if(total>262144)return finish('OUTPUT_LIMIT');chunks.push(b)});req.on('error',e=>finish('H2_STREAM_ERROR',e));req.on('end',()=>finish());req.end();});
});
}
