<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fallbackDomainModules, fetchDomainModules, type ModuleItem } from '@/api/modules'
import { createRecord, deleteRecord, fetchRecords, updateRecord, type RecordItem } from '@/api/records'
import { fetchTags, type TagItem } from '@/api/tags'
import AppLayout from '@/layouts/AppLayout.vue'
import { moduleLabel } from '@/utils/labels'

const records = ref<RecordItem[]>([])
const modules = ref<ModuleItem[]>(fallbackDomainModules)
const tags = ref<TagItem[]>([])
const loading = ref(false)
const apiOnline = ref(false)
const editDialogVisible = ref(false)
const editingRecordId = ref<number | null>(null)

const filters = reactive({
  moduleCode: '',
  tagId: undefined as number | undefined,
  recordDate: '',
  keyword: '',
})

const form = reactive({
  moduleCode: 'life',
  title: '',
  content: '',
  recordDate: new Date().toISOString().slice(0, 10),
  tagIds: [] as number[],
})

const editForm = reactive({
  moduleCode: 'life',
  title: '',
  content: '',
  recordDate: new Date().toISOString().slice(0, 10),
  tagIds: [] as number[],
})

async function loadRecords() {
  loading.value = true
  try {
    const [recordItems, domainModules, tagItems] = await Promise.all([
      fetchRecords({
        moduleCode: filters.moduleCode || undefined,
        tagId: filters.tagId,
        recordDate: filters.recordDate || undefined,
        keyword: filters.keyword.trim() || undefined,
      }),
      fetchDomainModules(),
      fetchTags(),
    ])
    records.value = recordItems
    modules.value = domainModules.filter((module) => module.enabled)
    tags.value = tagItems
    apiOnline.value = true
  } catch {
    apiOnline.value = false
  } finally {
    loading.value = false
  }
}

async function submitRecord() {
  if (!form.title.trim()) return
  await createRecord({ ...form })
  form.title = ''
  form.content = ''
  form.tagIds = []
  await loadRecords()
}

function openEditDialog(record: RecordItem) {
  editingRecordId.value = record.id
  editForm.moduleCode = record.moduleCode
  editForm.title = record.title
  editForm.content = record.content
  editForm.recordDate = record.recordDate
  editForm.tagIds = record.tags.map((tag) => tag.id)
  editDialogVisible.value = true
}

async function submitEditRecord() {
  if (editingRecordId.value === null || !editForm.title.trim()) return
  await updateRecord(editingRecordId.value, { ...editForm })
  editDialogVisible.value = false
  editingRecordId.value = null
  ElMessage.success('记录已更新')
  await loadRecords()
}

async function removeRecord(record: RecordItem) {
  try {
    await ElMessageBox.confirm(`确定删除「${record.title}」吗？`, '删除记录', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  await deleteRecord(record.id)
  ElMessage.success('记录已删除')
  await loadRecords()
}

function clearFilters() {
  filters.moduleCode = ''
  filters.tagId = undefined
  filters.recordDate = ''
  filters.keyword = ''
  loadRecords()
}

onMounted(loadRecords)
</script>

<template>
  <AppLayout>
    <header class="page-header">
      <div>
        <p class="eyebrow">记录管理</p>
        <h1>通用记录</h1>
        <p>用一套记录模型承载生活、学习、工作、兴趣和社交中的过程数据。</p>
        <span class="api-status" :class="{ online: apiOnline }">
          {{ apiOnline ? 'Records API 已连接' : '后端未连接，列表暂不可同步' }}
        </span>
      </div>
    </header>

    <section class="work-grid">
      <el-card shadow="never">
        <template #header>新增记录</template>
        <el-form label-position="top" @submit.prevent>
          <el-form-item label="模块">
            <el-select v-model="form.moduleCode">
              <el-option v-for="module in modules" :key="module.code" :label="module.name" :value="module.code" />
            </el-select>
          </el-form-item>
          <el-form-item label="标题">
            <el-input v-model="form.title" placeholder="记录标题" />
          </el-form-item>
          <el-form-item label="内容">
            <el-input v-model="form.content" type="textarea" :rows="4" placeholder="发生了什么？" />
          </el-form-item>
          <el-form-item label="日期">
            <el-date-picker v-model="form.recordDate" type="date" value-format="YYYY-MM-DD" />
          </el-form-item>
          <el-form-item label="标签">
            <el-select v-model="form.tagIds" multiple clearable placeholder="选择标签">
              <el-option v-for="tag in tags" :key="tag.id" :label="tag.name" :value="tag.id">
                <span class="tag-option">
                  <span class="tag-color" :style="{ backgroundColor: tag.color }" />
                  {{ tag.name }}
                </span>
              </el-option>
            </el-select>
          </el-form-item>
          <el-button type="primary" :loading="loading" @click="submitRecord">保存记录</el-button>
        </el-form>
      </el-card>

      <el-card shadow="never">
        <template #header>最近记录</template>
        <div class="filter-row">
          <el-select v-model="filters.moduleCode" clearable placeholder="按模块筛选" @change="loadRecords" @clear="loadRecords">
            <el-option v-for="module in modules" :key="module.code" :label="module.name" :value="module.code" />
          </el-select>
          <el-select v-model="filters.tagId" clearable placeholder="按标签筛选" @change="loadRecords" @clear="loadRecords">
            <el-option v-for="tag in tags" :key="tag.id" :label="tag.name" :value="tag.id" />
          </el-select>
          <el-date-picker v-model="filters.recordDate" type="date" value-format="YYYY-MM-DD" placeholder="按日期筛选" @change="loadRecords" />
          <el-input v-model="filters.keyword" clearable placeholder="搜索标题或内容" @keyup.enter="loadRecords" @clear="loadRecords" />
          <el-button @click="loadRecords">搜索</el-button>
          <el-button @click="clearFilters">清空</el-button>
        </div>

        <el-empty v-if="records.length === 0" description="暂无记录" />
        <div v-else class="item-list">
          <article v-for="record in records" :key="record.id" class="list-item">
            <div class="list-item-row">
              <strong>{{ record.title }}</strong>
              <div class="item-actions">
                <el-button size="small" text @click="openEditDialog(record)">编辑</el-button>
                <el-button size="small" text type="danger" @click="removeRecord(record)">删除</el-button>
              </div>
            </div>
            <span>{{ moduleLabel(record.moduleCode) }} · {{ record.recordDate }}</span>
            <div v-if="record.tags.length > 0" class="inline-tags">
              <el-tag v-for="tag in record.tags" :key="tag.id" size="small" :color="tag.color" effect="dark">
                {{ tag.name }}
              </el-tag>
            </div>
            <p>{{ record.content || '无内容' }}</p>
          </article>
        </div>
      </el-card>
    </section>

    <el-dialog v-model="editDialogVisible" title="编辑记录" width="520px">
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="模块">
          <el-select v-model="editForm.moduleCode">
            <el-option v-for="module in modules" :key="module.code" :label="module.name" :value="module.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="标题">
          <el-input v-model="editForm.title" placeholder="记录标题" />
        </el-form-item>
        <el-form-item label="内容">
          <el-input v-model="editForm.content" type="textarea" :rows="4" placeholder="发生了什么？" />
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker v-model="editForm.recordDate" type="date" value-format="YYYY-MM-DD" />
        </el-form-item>
        <el-form-item label="标签">
          <el-select v-model="editForm.tagIds" multiple clearable placeholder="选择标签">
            <el-option v-for="tag in tags" :key="tag.id" :label="tag.name" :value="tag.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="loading" @click="submitEditRecord">保存</el-button>
      </template>
    </el-dialog>
  </AppLayout>
</template>
