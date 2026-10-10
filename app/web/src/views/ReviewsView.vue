<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fallbackDomainModules, fetchDomainModules, type ModuleItem } from '@/api/modules'
import { createReview, deleteReview, fetchReviews, updateReview, type ReviewItem } from '@/api/reviews'
import AppLayout from '@/layouts/AppLayout.vue'
import { moduleLabel, reviewTypeLabel } from '@/utils/labels'

const reviews = ref<ReviewItem[]>([])
const modules = ref<ModuleItem[]>(fallbackDomainModules)
const loading = ref(false)
const apiOnline = ref(false)
const editDialogVisible = ref(false)
const editingReviewId = ref<number | null>(null)
const today = new Date().toISOString().slice(0, 10)
const weekStart = new Date(Date.now() - 6 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10)
const reviewTypeOptions = [{ label: '每周复盘', value: 'weekly' }, { label: '每月复盘', value: 'monthly' }, { label: '专题复盘', value: 'module' }]

const filters = reactive({
  reviewType: '',
  moduleCode: '',
  periodStart: '',
  periodEnd: '',
})

const form = reactive({
  reviewType: 'weekly',
  moduleCode: 'life',
  title: '',
  summary: '',
  highlights: '',
  problems: '',
  nextActions: '',
  periodStart: weekStart,
  periodEnd: today,
})

const editForm = reactive({
  reviewType: 'weekly',
  moduleCode: 'life',
  title: '',
  summary: '',
  highlights: '',
  problems: '',
  nextActions: '',
  periodStart: weekStart,
  periodEnd: today,
})

async function loadReviews() {
  loading.value = true
  try {
    const [reviewItems, domainModules] = await Promise.all([
      fetchReviews({
        reviewType: filters.reviewType || undefined,
        moduleCode: filters.moduleCode || undefined,
        periodStart: filters.periodStart || undefined,
        periodEnd: filters.periodEnd || undefined,
      }),
      fetchDomainModules(),
    ])
    reviews.value = reviewItems
    modules.value = domainModules.filter((module) => module.enabled)
    apiOnline.value = true
  } catch {
    apiOnline.value = false
  } finally {
    loading.value = false
  }
}

async function submitReview() {
  if (!form.title.trim()) return
  await createReview({ ...form })
  form.title = ''
  form.summary = ''
  form.highlights = ''
  form.problems = ''
  form.nextActions = ''
  ElMessage.success('复盘已创建')
  await loadReviews()
}

function resetFilters() {
  filters.reviewType = ''
  filters.moduleCode = ''
  filters.periodStart = ''
  filters.periodEnd = ''
  void loadReviews()
}

function openEditDialog(review: ReviewItem) {
  editingReviewId.value = review.id
  editForm.reviewType = review.reviewType
  editForm.moduleCode = review.moduleCode
  editForm.title = review.title
  editForm.summary = review.summary
  editForm.highlights = review.highlights
  editForm.problems = review.problems
  editForm.nextActions = review.nextActions
  editForm.periodStart = review.periodStart
  editForm.periodEnd = review.periodEnd
  editDialogVisible.value = true
}

async function submitEditReview() {
  if (editingReviewId.value === null || !editForm.title.trim()) return
  await updateReview(editingReviewId.value, { ...editForm })
  editDialogVisible.value = false
  editingReviewId.value = null
  ElMessage.success('复盘已更新')
  await loadReviews()
}

async function removeReview(review: ReviewItem) {
  try {
    await ElMessageBox.confirm(`确定删除「${review.title}」吗？`, '删除复盘', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  await deleteReview(review.id)
  ElMessage.success('复盘已删除')
  await loadReviews()
}

onMounted(loadReviews)
</script>

<template>
  <AppLayout>
    <header class="page-header">
      <div>
        <p class="eyebrow">复盘管理</p>
        <h1>复盘中心</h1>
        <p>把一周、一个月或某个模块的记录整理成判断和下一步行动。</p>
        <span class="api-status" :class="{ online: apiOnline }">
          {{ apiOnline ? '复盘服务已连接' : '后端未连接，列表暂不可同步' }}
        </span>
      </div>
    </header>

    <section class="work-grid">
      <el-card shadow="never">
        <template #header>新增复盘</template>
        <el-form label-position="top" @submit.prevent>
          <el-form-item label="类型">
            <el-segmented v-model="form.reviewType" :options="reviewTypeOptions" />
          </el-form-item>
          <el-form-item label="模块">
            <el-select v-model="form.moduleCode">
              <el-option v-for="module in modules" :key="module.code" :label="module.name" :value="module.code" />
            </el-select>
          </el-form-item>
          <el-form-item label="标题">
            <el-input v-model="form.title" placeholder="例如：本周工作回顾" />
          </el-form-item>
          <el-form-item label="周期">
            <div class="inline-fields">
              <el-date-picker v-model="form.periodStart" type="date" value-format="YYYY-MM-DD" />
              <el-date-picker v-model="form.periodEnd" type="date" value-format="YYYY-MM-DD" />
            </div>
          </el-form-item>
          <el-form-item label="总结">
            <el-input v-model="form.summary" type="textarea" :rows="3" />
          </el-form-item>
          <el-form-item label="亮点">
            <el-input v-model="form.highlights" type="textarea" :rows="2" />
          </el-form-item>
          <el-form-item label="问题">
            <el-input v-model="form.problems" type="textarea" :rows="2" />
          </el-form-item>
          <el-form-item label="下一步">
            <el-input v-model="form.nextActions" type="textarea" :rows="2" />
          </el-form-item>
          <el-button type="primary" :loading="loading" @click="submitReview">保存复盘</el-button>
        </el-form>
      </el-card>

      <el-card shadow="never">
        <template #header>复盘列表</template>
        <div class="filter-row">
          <el-select v-model="filters.reviewType" clearable placeholder="按类型筛选" @change="loadReviews" @clear="loadReviews">
            <el-option v-for="type in reviewTypeOptions" :key="type.value" :label="type.label" :value="type.value" />
          </el-select>
          <el-select v-model="filters.moduleCode" clearable placeholder="按模块筛选" @change="loadReviews" @clear="loadReviews">
            <el-option v-for="module in modules" :key="module.code" :label="module.name" :value="module.code" />
          </el-select>
          <el-date-picker v-model="filters.periodStart" type="date" value-format="YYYY-MM-DD" placeholder="开始日期" @change="loadReviews" />
          <el-date-picker v-model="filters.periodEnd" type="date" value-format="YYYY-MM-DD" placeholder="结束日期" @change="loadReviews" />
          <el-button @click="resetFilters">重置</el-button>
        </div>

        <el-empty v-if="reviews.length === 0" description="暂无复盘" />
        <div v-else class="item-list">
          <article v-for="review in reviews" :key="review.id" class="list-item">
            <div class="list-item-row">
              <strong>{{ review.title }}</strong>
              <div class="item-actions">
                <el-tag>{{ reviewTypeLabel(review.reviewType) }}</el-tag>
                <el-button size="small" text @click="openEditDialog(review)">编辑</el-button>
                <el-button size="small" text type="danger" @click="removeReview(review)">删除</el-button>
              </div>
            </div>
            <span>{{ moduleLabel(review.moduleCode) }} · {{ review.periodStart }} 至 {{ review.periodEnd }}</span>
            <p>{{ review.summary || '无总结' }}</p>
            <p v-if="review.nextActions">下一步：{{ review.nextActions }}</p>
          </article>
        </div>
      </el-card>
    </section>

    <el-dialog v-model="editDialogVisible" title="编辑复盘" width="620px">
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="类型">
          <el-segmented v-model="editForm.reviewType" :options="reviewTypeOptions" />
        </el-form-item>
        <el-form-item label="模块">
          <el-select v-model="editForm.moduleCode">
            <el-option v-for="module in modules" :key="module.code" :label="module.name" :value="module.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="标题">
          <el-input v-model="editForm.title" />
        </el-form-item>
        <el-form-item label="周期">
          <div class="inline-fields">
            <el-date-picker v-model="editForm.periodStart" type="date" value-format="YYYY-MM-DD" />
            <el-date-picker v-model="editForm.periodEnd" type="date" value-format="YYYY-MM-DD" />
          </div>
        </el-form-item>
        <el-form-item label="总结">
          <el-input v-model="editForm.summary" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="亮点">
          <el-input v-model="editForm.highlights" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="问题">
          <el-input v-model="editForm.problems" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="下一步">
          <el-input v-model="editForm.nextActions" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="loading" @click="submitEditReview">保存</el-button>
      </template>
    </el-dialog>
  </AppLayout>
</template>
