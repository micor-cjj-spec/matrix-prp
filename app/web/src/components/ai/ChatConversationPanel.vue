<script setup lang="ts">
import { computed, ref } from 'vue'
import { ChatDotRound, Close, Delete, Edit, Plus, MoreFilled } from '@element-plus/icons-vue'
import type { Conversation, AiUsage } from '@/api/ai'

const props = defineProps<{
  conversations: Conversation[]
  selectedId: string | null
  loading: boolean
  loadingMore: boolean
  hasMore: boolean
  error: boolean
  busy: boolean
  usage: AiUsage | null
  mobile?: boolean
}>()
const emit = defineEmits<{
  (e: 'select', id: string): void
  (e: 'new-chat'): void
  (e: 'rename', item: Conversation): void
  (e: 'remove', item: Conversation): void
  (e: 'load-more'): void
  (e: 'retry'): void
  (e: 'close'): void
}>()
const menuId = ref<string | null>(null)
const groups = computed(() => {
  const now = new Date()
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const day = 86400000
  const sections = [
    { label: '今天', items: [] as Conversation[] },
    { label: '昨天', items: [] as Conversation[] },
    { label: '近 7 天', items: [] as Conversation[] },
    { label: '近 30 天', items: [] as Conversation[] },
    { label: '更早', items: [] as Conversation[] },
  ]
  for (const chat of props.conversations) {
    const timestamp = new Date(chat.updatedAt).getTime()
    const age = Number.isFinite(timestamp) ? startToday - timestamp : 31 * day
    const index = age < 0 ? 0 : age < day ? 1 : age < 6 * day ? 2 : age < 29 * day ? 3 : 4
    sections[index].items.push(chat)
  }
  return sections.filter(section => section.items.length > 0)
})
function choose(id: string) {
  if (props.busy) return
  menuId.value = null
  emit('select', id)
}
function action(name: 'rename' | 'remove', item: Conversation) {
  menuId.value = null
  emit(name,item)
}
</script>

<template>
  <nav class="chat-conversation-panel" aria-label="聊天会话列表" @keydown.esc="menuId = null">
    <header class="chat-panel-top">
      <strong>PRP 助手</strong>
      <button v-if="mobile" type="button" class="chat-panel-icon" aria-label="关闭会话列表" @click="emit('close')">
        <el-icon><Close /></el-icon>
      </button>
    </header>
    <button type="button" class="chat-panel-new" :disabled="busy" @click="emit('new-chat')">
      <el-icon><Plus /></el-icon><span>新对话</span>
    </button>
    <div class="chat-panel-scroll">
      <template v-for="section in groups" :key="section.label">
        <p class="chat-panel-group">{{ section.label }}</p>
        <div v-for="item in section.items" :key="item.id" class="chat-panel-row"
          :class="{ selected: item.id === selectedId }">
          <button type="button" class="chat-panel-select" :disabled="busy"
            :title="item.title" :aria-current="item.id === selectedId ? 'page' : undefined"
            @click="choose(item.id)">
            <el-icon><ChatDotRound /></el-icon><span>{{ item.title }}</span>
          </button>
          <div class="chat-panel-actions">
            <button type="button" class="chat-panel-icon chat-panel-more"
              :aria-label="'管理会话：' + item.title" :aria-expanded="menuId === item.id"
              :disabled="busy" @click.stop="menuId = menuId === item.id ? null : item.id">
              <el-icon><MoreFilled /></el-icon>
            </button>
            <div v-if="menuId === item.id" class="chat-panel-menu" role="group" :aria-label="'管理' + item.title">
              <button type="button" @click.stop="action('rename', item)"><el-icon><Edit /></el-icon>重命名</button>
              <button type="button" class="danger" @click.stop="action('remove',item)"><el-icon><Delete /></el-icon>删除</button>
            </div>
          </div>
        </div>
      </template>
      <p v-if="loading && !conversations.length" class="chat-panel-note">正在加载历史会话…</p>
      <div v-else-if="error" class="chat-panel-note" role="alert">
        历史会话加载失败，已有记录未删除。
        <button type="button" @click="emit('retry')">重试</button>
      </div>
      <p v-else-if="!conversations.length" class="chat-panel-note">暂无历史会话</p>
      <button v-if="hasMore && !error" type="button" class="chat-panel-load"
        :disabled="loadingMore || loading" @click="emit('load-more')">
        {{ loadingMore ? '加载中…' : '加载更多会话' }}
      </button>
    </div>
    <footer v-if="usage" class="chat-panel-usage">
      本月 AI 请求 {{ usage.requests }} / {{ usage.maxRequests }}
    </footer>
  </nav>
</template>

<style scoped>
.chat-conversation-panel{display:flex;flex-direction:column;min-height:0;height:100%;background:#fbfcff;color:#29384e}
.chat-panel-top{display:flex;align-items:center;justify-content:space-between;padding:17px 15px 9px;gap:8px}
.chat-panel-top strong{font-size:17px}
.chat-panel-icon{width:30px;height:30px;display:grid;place-items:center;border:0;border-radius:9px;background:transparent;color:#7b899e;cursor:pointer}
.chat-panel-icon:hover,.chat-panel-icon:focus-visible{background:#e8eef7}
.chat-panel-new{display:flex;align-items:center;gap:10px;margin:6px 12px 14px;padding:11px 12px;border:1px solid #e1e9f3;border-radius:11px;text-align:left;background:white;color:#2b4161;cursor:pointer}
.chat-panel-new:disabled,.chat-panel-select:disabled{opacity:.55;cursor:not-allowed}
.chat-panel-scroll{flex:1;min-height:0;overflow-y:auto;padding:0 9px 18px;overscroll-behavior:contain}
.chat-panel-group{padding:13px 10px 6px;margin:0;font-size:11px;font-weight:600;color:#95a0b0}
.chat-panel-row{position:relative;display:flex;align-items:center;min-height:39px;border-radius:10px}
.chat-panel-row:hover,.chat-panel-row.selected{background:#e9f0fa}
.chat-panel-select{flex:1;min-width:0;display:flex;align-items:center;gap:9px;border:0;background:transparent;padding:10px 7px 10px 11px;text-align:left;color:#4b5e77;cursor:pointer}
.chat-panel-select span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px}
.chat-panel-actions{position:relative;flex:none}
.chat-panel-more{opacity:.4}
.chat-panel-row:hover .chat-panel-more,.chat-panel-more[aria-expanded=true],.chat-panel-more:focus-visible{opacity:1}
.chat-panel-menu{position:absolute;top:100%;right:0;min-width:130px;padding:5px;background:white;border:1px solid #e1e9f3;border-radius:10px;box-shadow:0 8px 23px #1a2d4b25;z-index:12}
.chat-panel-menu button{display:flex;align-items:center;gap:8px;width:100%;border:0;border-radius:7px;padding:9px 10px;background:white;text-align:left;color:#34475e;cursor:pointer;font-size:13px}
.chat-panel-menu button:hover{background:#f2f5fa}
.chat-panel-menu .danger{color:#c43b41}
.chat-panel-note{padding:12px;color:#8d9aa9;font-size:12px;line-height:1.6}
.chat-panel-note button{display:block;margin-top:8px;color:#3477e6;border:0;background:none;cursor:pointer}
.chat-panel-load{display:block;width:100%;border:0;background:none;color:#477dc8;padding:12px;cursor:pointer}
.chat-panel-usage{flex:none;border-top:1px solid #e9edf4;padding:13px 15px 16px;color:#94a0b0;font-size:12px}
</style>
