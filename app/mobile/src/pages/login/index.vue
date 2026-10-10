<script setup lang="ts">
import { reactive, ref } from 'vue'
import { login, registerAccount } from '@/api/auth'

const loading = ref(false)
const isRegister = ref(false)
const form = reactive({
  username: '',
  password: '',
  displayName: '',
  invitationCode: '',
})

async function submit() {
  if (!form.username.trim() || !form.password.trim()) {
    uni.showToast({ title: '请输入账号和密码', icon: 'none' })
    return
  }
  loading.value = true
  try {
    if (isRegister.value) {
      if (!form.displayName.trim() || !form.invitationCode.trim() || form.password.length < 12) {
        uni.showToast({ title: '请输入名称、邀请码及至少12位密码', icon: 'none' })
        return
      }
      await registerAccount(form.username, form.password, form.displayName, form.invitationCode)
    } else {
      await login(form.username, form.password)
    }
    uni.reLaunch({ url: '/pages/home/index' })
  } catch {
    uni.showToast({ title: isRegister.value ? '注册失败，请核对邀请码' : '登录失败', icon: 'none' })
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
      <text class="muted">{{ isRegister ? '凭邀请码创建个人账号' : '登录个人账号' }}</text>
      <input v-model="form.username" class="input" placeholder="账号" />
      <input v-model="form.password" class="input" password placeholder="密码" />
      <template v-if="isRegister">
        <input v-model="form.displayName" class="input" placeholder="显示名称" />
        <input v-model="form.invitationCode" class="input" placeholder="邀请码" />
      </template>
      <button class="button-primary" :loading="loading" @click="submit">{{ isRegister ? '注册并登录' : '登录' }}</button>
      <button class="button-secondary" @click="isRegister = !isRegister">{{ isRegister ? '已有账号？返回登录' : '收到邀请码？注册账号' }}</button>
    </view>
  </view>
</template>
