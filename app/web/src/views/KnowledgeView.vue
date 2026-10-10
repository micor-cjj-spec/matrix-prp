<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  fetchKnowledgeFile,
  fetchKnowledgeStats,
  fetchKnowledgeTree,
  searchKnowledge,
  type KnowledgeFile,
  type KnowledgeNode,
  type KnowledgeSearchResult,
  type KnowledgeStats,
} from '@/api/knowledge'
import AppLayout from '@/layouts/AppLayout.vue'

const tree = ref<KnowledgeNode[]>([])
const stats = ref<KnowledgeStats>({ fileCount: 0, directoryCount: 0, totalBytes: 0 })
const currentFile = ref<KnowledgeFile | null>(null)
const query = ref('')
const searchResults = ref<KnowledgeSearchResult[]>([])
const loading = ref(false)
const searching = ref(false)
const apiOnline = ref(false)

const renderedMarkdown = computed(() => (currentFile.value ? renderMarkdown(currentFile.value.content) : ''))
const statsItems = computed(() => [
  { label: 'Markdown 文件', value: String(stats.value.fileCount) },
  { label: '目录', value: String(stats.value.directoryCount) },
  { label: '总大小', value: formatBytes(stats.value.totalBytes) },
])

async function loadTree() {
  loading.value = true
  try {
    const [nextTree, nextStats] = await Promise.all([
      fetchKnowledgeTree(),
      fetchKnowledgeStats(),
    ])
    tree.value = nextTree
    stats.value = nextStats
    apiOnline.value = true
    const firstFile = findFirstFile(tree.value)
    if (firstFile) {
      await openFile(firstFile)
    }
  } catch {
    apiOnline.value = false
    stats.value = { fileCount: 0, directoryCount: 0, totalBytes: 0 }
  } finally {
    loading.value = false
  }
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

async function openFile(node: KnowledgeNode) {
  if (node.type !== 'file') return
  await openFileByPath(node.path)
}

async function openFileByPath(path: string) {
  currentFile.value = await fetchKnowledgeFile(path)
}

async function submitSearch() {
  if (!query.value.trim()) {
    searchResults.value = []
    return
  }
  searching.value = true
  try {
    searchResults.value = await searchKnowledge(query.value)
    apiOnline.value = true
  } catch {
    apiOnline.value = false
  } finally {
    searching.value = false
  }
}

function findFirstFile(nodes: KnowledgeNode[]): KnowledgeNode | null {
  for (const node of nodes) {
    if (node.type === 'file') return node
    const child = findFirstFile(node.children)
    if (child) return child
  }
  return null
}

function renderMarkdown(content: string) {
  const lines = content.replace(/\r\n/g, '\n').split('\n')
  const blocks: string[] = []
  let inCodeBlock = false
  let codeLines: string[] = []

  for (const line of lines) {
    if (line.trim().startsWith('```')) {
      if (inCodeBlock) {
        blocks.push(`<pre class="md-code-block"><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`)
        codeLines = []
      }
      inCodeBlock = !inCodeBlock
      continue
    }

    if (inCodeBlock) {
      codeLines.push(line)
      continue
    }

    const escaped = escapeHtml(line)
    if (!escaped.trim()) {
      blocks.push('<div class="md-space"></div>')
      continue
    }

    const heading = escaped.match(/^(#{1,4})\s+(.+)$/)
    if (heading) {
      const level = heading[1].length
      blocks.push(`<h${level} class="md-heading md-heading-${level}">${inlineMarkdown(heading[2])}</h${level}>`)
      continue
    }

    if (escaped.startsWith('&gt; ')) {
      blocks.push(`<blockquote class="md-quote">${inlineMarkdown(escaped.slice(5))}</blockquote>`)
      continue
    }

    if (/^[-*]\s+/.test(escaped)) {
      blocks.push(`<p class="md-list-item">${inlineMarkdown(escaped.replace(/^[-*]\s+/, ''))}</p>`)
      continue
    }

    if (/^\d+\.\s+/.test(escaped)) {
      blocks.push(`<p class="md-list-item ordered">${inlineMarkdown(escaped.replace(/^\d+\.\s+/, ''))}</p>`)
      continue
    }

    blocks.push(`<p>${inlineMarkdown(escaped)}</p>`)
  }

  if (codeLines.length > 0) {
    blocks.push(`<pre class="md-code-block"><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`)
  }

  return blocks.join('')
}

function inlineMarkdown(value: string) {
  return value
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code class="md-inline-code">$1</code>')
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

onMounted(loadTree)
</script>

<template>
  <AppLayout>
    <header class="page-header">
      <div>
        <p class="eyebrow">知识管理</p>
        <h1>知识库浏览</h1>
        <p>读取仓库里的 `knowledge/` 目录树，搜索并预览 Markdown 内容。</p>
        <span class="api-status" :class="{ online: apiOnline }">
          {{ apiOnline ? 'Knowledge API 已连接' : '后端未连接，知识库暂不可浏览' }}
        </span>
      </div>
    </header>

    <section class="metric-grid">
      <article v-for="item in statsItems" :key="item.label" class="metric-card">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </article>
    </section>

    <section class="knowledge-grid">
      <el-card shadow="never" class="knowledge-tree-card">
        <template #header>
          <div class="knowledge-tools">
            <span>目录</span>
            <el-input
              v-model="query"
              clearable
              placeholder="搜索 Markdown"
              @keyup.enter="submitSearch"
              @clear="searchResults = []"
            >
              <template #append>
                <el-button :loading="searching" @click="submitSearch">搜索</el-button>
              </template>
            </el-input>
          </div>
        </template>

        <div v-if="searchResults.length > 0" class="search-results">
          <article
            v-for="result in searchResults"
            :key="result.path"
            class="search-result"
            @click="openFileByPath(result.path)"
          >
            <div class="search-result-title">
              <strong>{{ result.name }}</strong>
              <em>匹配度 {{ result.score }}</em>
            </div>
            <span>{{ result.path }}</span>
            <p>{{ result.snippet }}</p>
          </article>
        </div>

        <el-empty v-if="tree.length === 0 && !loading" description="暂无目录" />
        <el-tree
          v-else-if="searchResults.length === 0"
          :data="tree"
          node-key="path"
          :props="{ label: 'name', children: 'children' }"
          default-expand-all
          @node-click="openFile"
        >
          <template #default="{ data }">
            <span class="knowledge-node" :class="{ file: data.type === 'file' }">
              {{ data.name }}
            </span>
          </template>
        </el-tree>
      </el-card>

      <el-card shadow="never" class="knowledge-reader-card">
        <template #header>
          <div class="reader-header">
            <span>{{ currentFile?.name || 'Markdown 阅读器' }}</span>
            <small v-if="currentFile">{{ currentFile.path }}</small>
          </div>
        </template>

        <el-empty v-if="!currentFile" description="请选择一个 Markdown 文件" />
        <article v-else class="markdown-reader" v-html="renderedMarkdown" />
      </el-card>
    </section>
  </AppLayout>
</template>
