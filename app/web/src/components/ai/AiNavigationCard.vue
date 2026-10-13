<script setup lang="ts">
import { computed } from 'vue'
import type { AiMessageBlock } from '@/api/ai'

const props = defineProps<{ block: AiMessageBlock }>()
// Defense-in-depth: never let model text or stored blocks become external links or javascript URLs.
const allowed = /^\/(?:tasks|wellness|finance|practice|records|videos|knowledge|apps)(?:\?(?:focus=\d+|date=\d{4}-\d{2}-\d{2}|month=\d{4}-\d{2}))?$/
const safeRoute = computed(() => allowed.test(props.block.route) ? props.block.route : null)
</script>

<template>
  <RouterLink v-if="safeRoute" :to="safeRoute" class="ai-navigation-card">
    <span class="ai-navigation-symbol">↗</span>
    <span class="ai-navigation-label">{{ block.label }}<small>在 PRP 中查看</small></span>
    <span aria-hidden="true" class="ai-navigation-arrow">›</span>
  </RouterLink>
</template>

<style scoped>
.ai-navigation-card{display:flex;align-items:center;gap:12px;max-width:360px;margin:10px 0;
  padding:13px 15px;border:1px solid #dbe7f9;border-radius:15px;background:#f8fbff;
  color:#245ca0;text-decoration:none;transition:background .15s,border-color .15s}
.ai-navigation-card:hover{background:#edf5ff;border-color:#b7cff5}
.ai-navigation-symbol{display:grid;place-items:center;width:33px;height:33px;border-radius:10px;
  color:#3975d7;background:#e6f0ff;font-size:21px}
.ai-navigation-label{flex:1;display:flex;flex-direction:column;gap:2px;font-weight:600;font-size:13px}
.ai-navigation-label small{color:#8392a8;font-size:11px;font-weight:400}
.ai-navigation-arrow{font-size:26px;color:#96add0}
</style>
