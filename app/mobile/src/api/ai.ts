import { getToken, clearToken, request } from './client'
export interface Conversation { id:string; title:string; updatedAt:string }
export interface ChatMessage { id:number; role:'user'|'assistant'; content:string; createdAt:string }
export interface Usage { month:string; requests:number; maxRequests:number; reservedTokens:number; maxReservedTokens:number }
export type ChatEvent = {event:'meta'|'delta'|'done'|'error';data:Record<string,unknown>}
export const listConversations = () => request<Conversation[]>({method:'GET',url:'/ai/conversations'})
export const listMessages = (id:string) => request<ChatMessage[]>({method:'GET',url:'/ai/conversations/'+encodeURIComponent(id)+'/messages'})
export const fetchUsage = () => request<Usage>({method:'GET',url:'/ai/usage'})
/** H5/PWA-only streaming adapter. Native uni-app would need a separate transport. */
export async function streamChat(id:string|null,content:string,onEvent:(e:ChatEvent)=>void,signal?:AbortSignal) {
  const response=await fetch('/api/ai/chat/stream',{
    method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+(getToken()??'')},
    body:JSON.stringify({conversationId:id,content}),signal,
  })
  if(response.status===401){clearToken();uni.reLaunch({url:'/pages/login/index'})}
  if(!response.ok||!response.body)throw new Error('AI HTTP '+response.status)
  const reader=response.body.getReader();const decoder=new TextDecoder();let buffer=''
  try{
    while(true){
      const {done,value}=await reader.read();if(done)break
      buffer+=decoder.decode(value,{stream:true}).replace(/\r\n/g,'\n')
      let boundary:number
      while((boundary=buffer.indexOf('\n\n'))>=0){
        const frame=buffer.slice(0,boundary);buffer=buffer.slice(boundary+2)
        const kind=frame.split('\n').find(x=>x.startsWith('event:'))?.slice(6).trim()
        const data=frame.split('\n').filter(x=>x.startsWith('data:')).map(x=>x.slice(5).trimStart()).join('\n')
        if(kind&&data&&['meta','delta','done','error'].includes(kind))
          onEvent({event:kind as ChatEvent['event'],data:JSON.parse(data) as Record<string,unknown>})
      }
    }
  }finally{reader.releaseLock()}
}
