// Ordinary task scopes are intentionally narrower than bootstrap/governance scopes.
const ROOTS=Object.freeze([
 'app/backend/src/main/java/',
 'app/backend/src/test/java/',
 'app/web/src/',
 'app/mobile/src/',
 'app/docs/ai-notes/',
 'app/docs/api/',
 'app/docs/bugs/',
 'app/docs/data/',
 'app/docs/decisions/',
 'app/docs/features/',
 'app/docs/product/',
 'app/docs/releases/',
 'app/docs/technical/',
 'app/docs/README.md'
])
const SAFE_PATH=/^[a-zA-Z0-9_.\/-]+$/
function safePath(path){
 return typeof path==='string'&&path.length>3&&path.length<=200&&
  SAFE_PATH.test(path)&&!path.startsWith('/')&&!path.includes('//')&&
  !path.split('/').includes('..')&&!path.split('/').includes('.')&&
  !path.startsWith('.git/')&&path.includes('/')
}
function overlaps(a,b){
 return a===b||(a.endsWith('/')&&b.startsWith(a))||
  (b.endsWith('/')&&a.startsWith(b))
}
export function validateTaskScopeList(paths){
 if(!Array.isArray(paths)||paths.length<1||paths.length>20)return false
 if(!paths.every(safePath))return false
 if(new Set(paths).size!==paths.length)return false
 for(let i=0;i<paths.length;i++)for(let j=i+1;j<paths.length;j++)
  if(overlaps(paths[i],paths[j]))return false
 return paths.every(path=>ROOTS.some(root=>path===root||
  (root.endsWith('/')&&path.startsWith(root))))
}
export function ordinaryTaskScopeRoots(){return [...ROOTS]}
