<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { fallbackDomainModules, fetchDomainModules, type ModuleItem } from '@/api/modules'
import { createRecord } from '@/api/records'

const modules = ref<ModuleItem[]>(fallbackDomainModules)
const moduleIndex = ref(0)
const loading = ref(false)
const form = reactive({
  moduleCode: 'life',
  title: '',
  content: '',
  recordDate: new Date().toISOString().slice(0, 10),
})

const moduleNames = computed(() => modules.value.map((module) => module.name))
const selectedModuleName = computed(() => modules.value[moduleIndex.value]?.name ?? form.moduleCode)

function changeModule(event: { detail: { value: number | string } }) {
  const nextIndex = Number(event.detail.value)
  moduleIndex.value = nextIndex
  form.moduleCode = modules.value[nextIndex]?.code ?? form.moduleCode
}

function goHome() {
  uni.reLaunch({ url: '/pages/home/index' })
}

async function submit() {
  if (!form.title.trim()) {
    uni.showToast({ title: '请输入标题', icon: 'none' })
    return
  }
  loading.value = true
  try {
    await createRecord({ ...form })
    form.title = ''
    form.content = ''
    uni.showToast({ title: '已保存', icon: 'success' })
  } catch {
    uni.showToast({ title: '保存失败', icon: 'none' })
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
        <view class="title">快速记录</view>
        <text class="muted">把生活、学习、工作里的关键信息先记下来。</text>
      </view>
    </view>

    <view class="panel stack">
      <picker class="select" :value="moduleIndex" :range="moduleNames" @change="changeModule">
        <view>{{ selectedModuleName }}</view>
      </picker>
      <input v-model="form.title" class="input" placeholder="标题" />
      <textarea v-model="form.content" class="textarea" placeholder="发生了什么？" />
      <input v-model="form.recordDate" class="input" placeholder="YYYY-MM-DD" />
      <button class="button-primary" :loading="loading" @click="submit">保存记录</button>
      <button class="button-secondary" @click="goHome">返回今日</button>
    </view>
  </view>
</template>
