<script setup lang="ts">
import { ChatDotRound, Lock, Reading, Connection } from '@element-plus/icons-vue'
import AppLayout from '@/layouts/AppLayout.vue'
</script>

<template>
  <AppLayout>
    <div class="prp-chat-page">
      <header class="prp-section-header">
        <div><p class="eyebrow">MATRIX AI</p><h1>AI 聊天</h1>
          <p>未来，你可以在这里与智能助手交流，并连接个人应用。</p></div>
      </header>
      <div class="prp-chat-empty">
        <span class="prp-chat-emblem"><el-icon><ChatDotRound /></el-icon></span>
        <h2>统一聊天入口已准备好</h2>
        <p>当前 main 分支尚未集成完整的 Matrix AI Orchestrator 聊天服务。
          为避免误导，此页面暂不提供无法发送的聊天输入框。</p>
        <div class="prp-chat-capabilities">
          <span><el-icon><Reading /></el-icon> 学习问答与解题</span>
          <span><el-icon><Connection /></el-icon> 多应用工具接入</span>
          <span><el-icon><Lock /></el-icon> 按账号隔离会话</span>
        </div>
        <RouterLink to="/apps" class="prp-inline-link">先去使用现有应用 →</RouterLink>
      </div>
    </div>
  </AppLayout>
</template>
