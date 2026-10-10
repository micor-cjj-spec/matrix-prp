<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createTag, deleteTag, fetchTags, updateTag, type TagItem } from '@/api/tags'
import AppLayout from '@/layouts/AppLayout.vue'

const tags = ref<TagItem[]>([])
const loading = ref(false)
const apiOnline = ref(false)
const editDialogVisible = ref(false)
const editingId = ref<number | null>(null)

const form = reactive({
  name: '',
  color: '#1d4ed8',
  description: '',
})

const editForm = reactive({
  name: '',
  color: '#1d4ed8',
  description: '',
})

async function loadTags() {
  loading.value = true
  try {
    tags.value = await fetchTags()
    apiOnline.value = true
  } catch {
    apiOnline.value = false
  } finally {
    loading.value = false
  }
}

async function submitTag() {
  if (!form.name.trim()) return
  await createTag({ ...form })
  form.name = ''
  form.description = ''
  ElMessage.success('标签已创建')
  await loadTags()
}

function openEdit(tag: TagItem) {
  editingId.value = tag.id
  editForm.name = tag.name
  editForm.color = tag.color
  editForm.description = tag.description
  editDialogVisible.value = true
}

async function submitEdit() {
  if (!editingId.value || !editForm.name.trim()) return
  await updateTag(editingId.value, { ...editForm })
  editDialogVisible.value = false
  ElMessage.success('标签已更新')
  await loadTags()
}

async function removeTag(tag: TagItem) {
  await ElMessageBox.confirm(`确认删除标签「${tag.name}」？`, '删除标签', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  })
  await deleteTag(tag.id)
  ElMessage.success('标签已删除')
  await loadTags()
}

onMounted(loadTags)
</script>

<template>
  <AppLayout>
    <header class="page-header">
      <div>
        <p class="eyebrow">标签管理</p>
        <h1>标签管理</h1>
        <p>维护一套跨记录、任务、财务和复盘通用的标签字典，让后续检索和分析更稳定。</p>
        <span class="api-status" :class="{ online: apiOnline }">
          {{ apiOnline ? 'Tags API 已连接' : '后端未连接，列表暂不可同步' }}
        </span>
      </div>
    </header>

    <section class="work-grid">
      <el-card shadow="never">
        <template #header>新增标签</template>
        <el-form label-position="top" @submit.prevent>
          <el-form-item label="名称">
            <el-input v-model="form.name" placeholder="例如：学习、工作、重要" />
          </el-form-item>
          <el-form-item label="颜色">
            <el-color-picker v-model="form.color" />
          </el-form-item>
          <el-form-item label="说明">
            <el-input v-model="form.description" type="textarea" :rows="3" />
          </el-form-item>
          <el-button type="primary" :loading="loading" @click="submitTag">保存标签</el-button>
        </el-form>
      </el-card>

      <el-card shadow="never">
        <template #header>标签列表</template>
        <el-empty v-if="tags.length === 0" description="暂无标签" />
        <div v-else class="tag-list">
          <article v-for="tag in tags" :key="tag.id" class="tag-item">
            <span class="tag-color" :style="{ backgroundColor: tag.color }" />
            <div>
              <strong>{{ tag.name }}</strong>
              <p>{{ tag.description || '无说明' }}</p>
            </div>
            <div class="item-actions">
              <el-button size="small" @click="openEdit(tag)">编辑</el-button>
              <el-button size="small" type="danger" plain @click="removeTag(tag)">删除</el-button>
            </div>
          </article>
        </div>
      </el-card>
    </section>

    <el-dialog v-model="editDialogVisible" title="编辑标签" width="420px">
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="名称">
          <el-input v-model="editForm.name" />
        </el-form-item>
        <el-form-item label="颜色">
          <el-color-picker v-model="editForm.color" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="editForm.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>
  </AppLayout>
</template>
