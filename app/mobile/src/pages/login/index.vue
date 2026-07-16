<script setup lang="ts">
import { reactive, ref } from 'vue'
import { login } from '@/api/auth'

const loading = ref(false)
const form = reactive({
  username: 'admin',
  password: 'matrix-prp',
})

async function submit() {
  if (!form.username.trim() || !form.password.trim()) {
    uni.showToast({ title: '请输入账号和密码', icon: 'none' })
    return
  }
  loading.value = true
  try {
    await login(form.username, form.password)
    uni.reLaunch({ url: '/pages/home/index' })
  } catch {
    uni.showToast({ title: '登录失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <view class="screen">
    <view class="brand-row">
      <view class="brand-mark">M</view>
      <view>
        <view class="title">Matrix PRP</view>
        <text class="muted">个人资源管理平台</text>
      </view>
    </view>

    <view class="panel stack">
      <text class="muted">一期移动端</text>
      <input v-model="form.username" class="input" placeholder="账号" />
      <input v-model="form.password" class="input" password placeholder="密码" />
      <button class="button-primary" :loading="loading" @click="submit">登录</button>
    </view>
  </view>
</template>
