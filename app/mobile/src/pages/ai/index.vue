<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { fetchUsage, listConversations, listMessages, streamChat, type ChatMessage, type Conversation, type Usage } from '@/api/ai'
const conversations=ref<Conversation[]>([])
const messages=ref<ChatMessage[]>([])
const current=ref<string|null>(null)
const input=ref('')
const busy=ref(false)
const usage=ref<Usage|null>(null)
let controller:AbortController|null=null
async function reload(){
  try{
    const [items,used]=await Promise.all([listConversations(),fetchUsage()])
    conversations.value=items;usage.value=used
  }catch{uni.showToast({title:'AI 会话加载失败',icon:'none'})}
}
async function openConversation(id:string){
  if(busy.value)return
  current.value=id
  try{messages.value=await listMessages(id)}
  catch{uni.showToast({title:'聊天记录读取失败',icon:'none'})}
}
function newChat(){if(busy.value)return;current.value=null;messages.value=[]}
async function send(){
  const content=input.value.trim()
  if(!content||busy.value||content.length>4000)return
  busy.value=true;input.value=''
  messages.value.push(
    {id:-Date.now(),role:'user',content,createdAt:new Date().toISOString()},
    {id:-Date.now()-1,role:'assistant',content:'',createdAt:new Date().toISOString()}
  )
  const assistant=messages.value[messages.value.length-1]
  controller=new AbortController()
  let finished=false
  try{
    await streamChat(current.value,content,({event,data})=>{
      if(event==='meta')current.value=String(data.conversationId)
      if(event==='delta')assistant.content+=String(data.text??'')
      if(event==='done')finished=true
      if(event==='error')throw new Error(String(data.message??'请求失败'))
    },controller.signal)
    if(!finished)throw new Error('Stream interrupted')
  }catch{uni.showToast({title:'AI 请求失败或额度已满',icon:'none'})}
  finally{
    busy.value=false;controller=null;await reload()
    if(current.value){
      try{messages.value=await listMessages(current.value)}
      catch{ /* preserve streaming preview */ }
    }
  }
}
onMounted(reload)
onBeforeUnmount(()=>controller?.abort())
</script>
<template>
  <view class="screen">
    <view class="brand-row">
      <view class="brand-mark">AI</view>
      <view><view class="title">PRP 助手</view><text class="muted">你的个人智能助手</text></view>
    </view>
    <view class="section">
      <view class="chat-actions">
        <button class="mini-button" :disabled="busy" @click="newChat">+ 新对话</button>
        <text v-if="usage" class="muted">本月 {{ usage.requests }}/{{ usage.maxRequests }} 次</text>
      </view>
      <scroll-view scroll-x class="history"><view class="history-row">
        <button v-for="item in conversations" :key="item.id" class="history-button"
          :class="{selected:current===item.id}" :disabled="busy" @click="openConversation(item.id)">{{ item.title }}</button>
      </view></scroll-view>
    </view>
    <scroll-view scroll-y class="chat-messages">
      <view v-if="!messages.length" class="empty">你好！可以让我辅助学习、整理思路或回答问题。</view>
      <view v-for="(message,i) in messages" :key="message.id||i" class="chat-bubble"
        :class="{mine:message.role==='user'}">
        <text class="muted">{{ message.role==='user'?'我':'PRP 助手' }}</text>
        <text class="bubble-text">{{ message.content||'正在思考...' }}</text>
      </view>
    </scroll-view>
    <view class="chat-entry">
      <textarea v-model="input" class="chat-input" maxlength="4000" :disabled="busy"
        placeholder="输入问题..." auto-height />
      <button class="mini-button send-button" :disabled="busy||!input.trim()" @click="send">{{ busy?'回复中...':'发送' }}</button>
    </view>
    <text class="muted disclaimer">AI 回答可能有误，敏感信息请谨慎提交。</text>
  </view>
</template>
<style scoped>
.chat-actions{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.history{white-space:nowrap}.history-row{display:flex;gap:8px}
.history-button{flex:0 0 auto;max-width:170px;overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap;font-size:12px;background:#fff;border-radius:10px;padding:6px 9px}
.history-button.selected{background:#dbeafe;color:#1d4ed8}
.chat-messages{height:48vh;background:#fff;padding:12px;box-sizing:border-box;border-radius:12px}
.chat-bubble{max-width:88%;background:#f1f5f9;padding:11px;border-radius:12px;margin:10px 0;box-sizing:border-box}
.chat-bubble.mine{margin-left:auto;background:#dbeafe}
.bubble-text{display:block;white-space:pre-wrap;overflow-wrap:anywhere;margin-top:6px;font-size:14px}
.chat-entry{display:flex;align-items:end;gap:8px;margin-top:14px}
.chat-input{flex:1;min-height:54px;max-height:120px;padding:10px;background:#fff;border-radius:10px;
  font-size:14px;box-sizing:border-box}
.send-button{flex:0 0 auto}.disclaimer{display:block;font-size:11px;margin:12px 0}
</style>
