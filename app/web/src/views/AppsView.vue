<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { Component } from 'vue'
import {
  Bell, Calendar, Collection, CollectionTag, Document, EditPen, Food,
  Grid, House, Money, Notebook, Reading, Search, Star, Tickets, VideoCamera,
} from '@element-plus/icons-vue'
import AppLayout from '@/layouts/AppLayout.vue'
import { useAuthStore } from '@/stores/auth'
import { getAppEntries, groupNames, groupOrder, type AppEntry, type AppGroup } from '@/utils/appCatalog'

const auth = useAuthStore()
const query = ref('')
const category = ref<AppGroup | 'all'>('all')
const favorites = ref<string[]>([])
const preferenceKey = computed(() => 'matrix-prp:favorite-apps:' + (auth.user?.id ?? 'anonymous'))
const entries = computed(() => getAppEntries(Boolean(auth.user?.administrator)))
const filtered = computed(() => entries.value.filter(item =>
  (category.value === 'all' || item.group === category.value)
  && (item.name.toLocaleLowerCase().includes(query.value.trim().toLocaleLowerCase())
    || groupNames[item.group].includes(query.value.trim()))))
const favoriteApps = computed(() => entries.value.filter(item => favorites.value.includes(item.code)))
const categories = computed(() => groupOrder.filter(group => entries.value.some(item => item.group === group)))
const icons: Record<string, Component> = {
  learning: Reading, wellness: Food, life: House, finance: Money,
  videos: VideoCamera, practice: Collection, knowledge: Notebook,
  tasks: Tickets, records: Document, reviews: EditPen, tags: CollectionTag,
  notifications: Bell,
}
function iconFor(item: AppEntry): Component { return icons[item.code] ?? Grid }
function loadFavorites() {
  try {
    const saved: unknown = JSON.parse(localStorage.getItem(preferenceKey.value) || 'null')
    favorites.value = Array.isArray(saved) && saved.every(v => typeof v === 'string')
      ? saved : ['learning', 'wellness', 'life', 'finance']
  } catch { favorites.value = ['learning', 'wellness', 'life', 'finance'] }
}
watch(preferenceKey, loadFavorites, { immediate: true })
function toggleFavorite(code: string) {
  favorites.value = favorites.value.includes(code)
    ? favorites.value.filter(v => v !== code)
    : [...favorites.value, code]
  try { localStorage.setItem(preferenceKey.value, JSON.stringify(favorites.value)) } catch { /* storage disabled */ }
}
</script>

<template>
  <AppLayout>
    <div class="prp-apps-page">
      <header class="prp-section-header">
        <div><p class="eyebrow">APP CENTER</p><h1>应用中心</h1>
          <p>找到你需要的工具，让学习、生活和工作井井有条。</p></div>
      </header>
      <div class="prp-apps-search">
        <el-input v-model="query" :prefix-icon="Search" clearable
          size="large" placeholder="搜索应用名称或分类" aria-label="搜索应用" />
      </div>
      <section v-if="favoriteApps.length && !query && category === 'all'" class="prp-apps-section">
        <h2>我的常用</h2>
        <div class="prp-apps-grid">
          <RouterLink v-for="item in favoriteApps" :key="'favorite-' + item.code"
            :to="item.route" class="prp-app-card">
            <span class="prp-app-icon"><el-icon><component :is="iconFor(item)" /></el-icon></span>
            <span class="prp-app-card-copy"><strong>{{ item.name }}</strong>
              <small>{{ groupNames[item.group] }} · {{ item.kind === 'domain' ? '应用空间' : '功能工具' }}</small></span>
          </RouterLink>
        </div>
      </section>
      <section class="prp-apps-section">
        <div class="prp-apps-section-heading"><h2>全部应用</h2><span>{{ filtered.length }} 个可用入口</span></div>
        <div class="prp-app-filters" aria-label="应用分类">
          <button type="button" :class="{ selected: category === 'all' }" :aria-pressed="category === 'all'"
            @click="category = 'all'">全部</button>
          <button v-for="group in categories" :key="group" type="button"
            :class="{ selected: category === group }" :aria-pressed="category === group"
            @click="category = group">{{ groupNames[group] }}</button>
        </div>
        <div v-if="filtered.length" class="prp-apps-grid">
          <div v-for="item in filtered" :key="item.code" class="prp-app-entry">
            <RouterLink :to="item.route" class="prp-app-card">
              <span class="prp-app-icon"><el-icon><component :is="iconFor(item)" /></el-icon></span>
              <span class="prp-app-card-copy"><strong>{{ item.name }}</strong>
                <small>{{ groupNames[item.group] }} · {{ item.kind === 'domain' ? '应用空间' : '功能工具' }}</small></span>
            </RouterLink>
            <button type="button" class="prp-favorite-button" :class="{ selected: favorites.includes(item.code) }"
              :aria-label="favorites.includes(item.code) ? '取消常用：' + item.name : '添加常用：' + item.name"
              :aria-pressed="favorites.includes(item.code)" @click="toggleFavorite(item.code)">
              <el-icon><Star /></el-icon>
            </button>
          </div>
        </div>
        <p v-else class="prp-apps-empty">没有找到匹配的应用，试试其他关键词或分类。</p>
      </section>
      <p class="prp-apps-note">应用入口从功能注册中心生成。收藏仅影响当前浏览器的快捷显示，不会修改业务数据。</p>
    </div>
  </AppLayout>
</template>
