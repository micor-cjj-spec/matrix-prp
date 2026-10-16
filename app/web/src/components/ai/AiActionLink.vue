<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { apiClient, type ApiResponse } from '@/api/client'
const props = defineProps<{ draftId: string; refreshKey: number }>()
const emit = defineEmits<{ open: [id: string] }>()
type Status = 'PENDING' | 'CONSUMED' | 'EXPIRED' | 'LOADING' | 'UNKNOWN'
const status = ref<Status>('LOADING')
const router = useRouter()
const href = computed(() => router.resolve({ name: 'chat', query: { action: props.draftId } }).href)
let serial = 0
watch(() => [props.draftId, props.refreshKey], async () => {
  const current = ++serial
  status.value = 'LOADING'
  try {
    const result = await apiClient.get<ApiResponse<{ status: Status }>>(
      '/wellness/ai/drafts/' + encodeURIComponent(props.draftId))
    if (current === serial) status.value = result.data.data.status
  } catch {
    if (current === serial) status.value = 'UNKNOWN'
  }
}, { immediate: true })
</script>

<template>
  <div class="ai-action-link-line">
    <a :href="href" @click.prevent="emit('open', draftId)">
      ↗ {{ status === 'CONSUMED' ? '查看 / 修改健康记录' : '查看 / 填写健康记录' }}
    </a>
    <span v-if="status === 'CONSUMED'" class="ai-action-saved-label">已保存</span>
    <span v-else-if="status === 'PENDING'">待确认</span>
    <span v-else-if="status === 'EXPIRED'">已过期</span>
    <span v-else-if="status === 'UNKNOWN'">状态待读取</span>
  </div>
</template>

<style scoped>
.ai-action-link-line{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin:6px 0;font-size:14px}
.ai-action-link-line a{color:#2563eb;text-decoration:underline;text-underline-offset:3px;cursor:pointer;font-weight:550}
.ai-action-link-line a:focus-visible{outline:2px solid #2563eb;outline-offset:3px}
.ai-action-link-line span{font-size:12px;color:#64748b}
.ai-action-link-line .ai-action-saved-label{color:#168053}
</style>
