<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { fallbackDomainModules, fetchDomainModules, type ModuleItem } from '@/api/modules'
import { createTask } from '@/api/tasks'

const modules = ref<ModuleItem[]>(fallbackDomainModules)
const moduleIndex = ref(0)
const priorityIndex = ref(1)
const loading = ref(false)

const priorityOptions = [
  { label: '低优先级', value: 'low' },
  { label: '中优先级', value: 'medium' },
  { label: '高优先级', value: 'high' },
]

const form = reactive({
  moduleCode: 'life',
  title: '',
  description: '',
  priority: 'medium',
  dueDate: new Date().toISOString().slice(0, 10),
})

const moduleNames = computed(() => modules.value.map((module) => module.name))
const selectedModuleName = computed(() => modules.value[moduleIndex.value]?.name ?? form.moduleCode)
const priorityNames = computed(() => priorityOptions.map((item) => item.label))
const selectedPriorityName = computed(() => priorityOptions[priorityIndex.value]?.label ?? form.priority)

function changeModule(event: { detail: { value: number | string } }) {
  const nextIndex = Number(event.detail.value)
  moduleIndex.value = nextIndex
  form.moduleCode = modules.value[nextIndex]?.code ?? form.moduleCode
}

function changePriority(event: { detail: { value: number | string } }) {
  const nextIndex = Number(event.detail.value)
  priorityIndex.value = nextIndex
  form.priority = priorityOptions[nextIndex]?.value ?? form.priority
}

function goHome() {
  uni.reLaunch({ url: '/pages/home/index' })
}

async function submit() {
  if (!form.title.trim()) {
    uni.showToast({ title: '请输入任务标题', icon: 'none' })
    return
  }
  loading.value = true
  try {
    await createTask({ ...form })
    form.title = ''
    form.description = ''
    uni.showToast({ title: '已创建', icon: 'success' })
  } catch {
    uni.showToast({ title: '创建失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    const remoteModules = await fetchDomainModules()
    modules.value = remoteModules.filter((module) => module.enabled)
    moduleIndex.value = Math.max(0, modules.value.findIndex((module) => module.code === form.moduleCode))
  } catch {
    modules.value = fallbackDomainModules
  }
})
</script>

<template>
  <view class="screen">
    <view class="brand-row">
      <view>
        <view class="title">快速任务</view>
        <text class="muted">把下一步行动直接放进今日待办和任务概览。</text>
      </view>
    </view>

    <view class="panel stack">
      <picker class="select" :value="moduleIndex" :range="moduleNames" @change="changeModule">
        <view>{{ selectedModuleName }}</view>
      </picker>
      <input v-model="form.title" class="input" placeholder="任务标题" />
      <textarea v-model="form.description" class="textarea" placeholder="要完成什么？" />
      <picker class="select" :value="priorityIndex" :range="priorityNames" @change="changePriority">
        <view>{{ selectedPriorityName }}</view>
      </picker>
      <input v-model="form.dueDate" class="input" placeholder="YYYY-MM-DD" />
      <button class="button-primary" :loading="loading" @click="submit">保存任务</button>
      <button class="button-secondary" @click="goHome">返回今日</button>
    </view>
  </view>
</template>
