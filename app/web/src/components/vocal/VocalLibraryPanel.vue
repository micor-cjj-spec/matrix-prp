<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Headset, List, Calendar, EditPen, Plus, Delete, Check, Collection,
} from '@element-plus/icons-vue'
import {
  vocalApi,
  type VocalSong, type VocalSongRequest, type VocalSection, type VocalSectionRequest,
  type VocalLesson, type VocalLessonRequest, type VocalAssignment, type VocalAssignmentRequest,
} from '@/api/vocal'

const emit = defineEmits<{
  (event: 'association-change', value: { songId: number | null; sectionId: number | null }): void
}>()

const songs = ref<VocalSong[]>([])
const sections = ref<VocalSection[]>([])
const lessons = ref<VocalLesson[]>([])
const assignments = ref<VocalAssignment[]>([])
const selectedSongId = ref<number | null>(null)
const selectedSectionId = ref<number | null>(null)
const busy = ref(false)

const songDialog = ref(false)
const editingSongId = ref<number | null>(null)
const songDraft = reactive<VocalSongRequest>({ title: '', artist: '', originalKey: '', status: 'LEARNING', note: '' })

const sectionDialog = ref(false)
const editingSectionId = ref<number | null>(null)
const sectionDraft = reactive<VocalSectionRequest>({
  title: '', startMarker: '', endMarker: '', focus: '', sortOrder: 0,
})

const lessonDialog = ref(false)
const editingLessonId = ref<number | null>(null)
const lessonDraft = reactive<VocalLessonRequest>({
  lessonDate: localToday(), teacherName: '', summary: '', feedback: '',
})

const assignmentDialog = ref(false)
const editingAssignmentId = ref<number | null>(null)
const assignmentSections = ref<VocalSection[]>([])
const assignmentDraft = reactive<VocalAssignmentRequest>({
  lessonId: null, songId: null, sectionId: null, title: '', detail: '', dueDate: null, status: 'TODO',
})

function localToday() {
  const date = new Date()
  return [date.getFullYear(), String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0')].join('-')
}
function emitAssociation() {
  emit('association-change', { songId: selectedSongId.value, sectionId: selectedSectionId.value })
}
function songStatus(status: VocalSong['status']) {
  return status === 'PLANNED' ? '待练习' : status === 'MASTERED' ? '基本掌握' : '练习中'
}
function assignmentStatus(status: VocalAssignment['status']) {
  return status === 'DONE' ? '已完成' : status === 'IN_PROGRESS' ? '进行中' : '待练习'
}
function assignmentTag(status: VocalAssignment['status']) {
  return status === 'DONE' ? 'success' : status === 'IN_PROGRESS' ? 'warning' : 'info'
}
async function refreshSongs() {
  songs.value = await vocalApi.songs()
  if (selectedSongId.value && !songs.value.some(song => song.id === selectedSongId.value)) {
    selectedSongId.value = null
    selectedSectionId.value = null
  }
}
async function refreshLessons() {
  lessons.value = await vocalApi.lessons()
}
async function refreshAssignments() {
  assignments.value = await vocalApi.assignments()
}
async function refreshAll() {
  busy.value = true
  try {
    await Promise.all([refreshSongs(), refreshLessons(), refreshAssignments()])
  } catch {
    ElMessage.error('声乐曲目或课程数据加载失败，请确认数据库迁移与后端版本已更新')
  } finally {
    busy.value = false
  }
}
watch(selectedSongId, async songId => {
  selectedSectionId.value = null
  sections.value = []
  emitAssociation()
  if (!songId) return
  try {
    sections.value = await vocalApi.sections(songId)
  } catch {
    ElMessage.error('歌曲段落加载失败')
  }
})
watch(selectedSectionId, emitAssociation)
watch(() => assignmentDraft.songId, async songId => {
  assignmentDraft.sectionId = null
  assignmentSections.value = []
  if (!songId) return
  try { assignmentSections.value = await vocalApi.sections(songId) }
  catch { ElMessage.error('作业关联的歌曲段落加载失败') }
})

onMounted(() => {
  emitAssociation()
  void refreshAll()
})

function openSong(song?: VocalSong) {
  editingSongId.value = song?.id ?? null
  Object.assign(songDraft, song ? {
    title: song.title, artist: song.artist, originalKey: song.originalKey,
    status: song.status, note: song.note,
  } : { title: '', artist: '', originalKey: '', status: 'LEARNING', note: '' })
  songDialog.value = true
}
async function saveSong() {
  if (!songDraft.title.trim()) { ElMessage.warning('请填写歌曲名称'); return }
  busy.value = true
  try {
    const saved = await vocalApi.saveSong({ ...songDraft }, editingSongId.value ?? undefined)
    await refreshSongs()
    songDialog.value = false
    selectedSongId.value = saved.id
    ElMessage.success(editingSongId.value ? '歌曲信息已更新' : '歌曲已加入曲库')
  } catch {
    ElMessage.error('歌曲保存失败')
  } finally { busy.value = false }
}
async function removeSong(song: VocalSong) {
  try {
    await ElMessageBox.confirm('删除曲目会同时删除它的段落；历史录音、课程作业不会删除，但关联曲目会清空。', '删除曲目', { type: 'warning' })
    await vocalApi.removeSong(song.id)
    await Promise.all([refreshSongs(), refreshLessons(), refreshAssignments()])
    if (selectedSongId.value === song.id) {
      selectedSongId.value = null
      selectedSectionId.value = null
    }
    ElMessage.success('曲目已删除，历史录音仍保留')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error('删除曲目失败')
  }
}
async function manageSections(song: VocalSong) {
  selectedSongId.value = song.id
  await Promise.resolve()
  document.getElementById('vocal-section-editor')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}
function openSection(section?: VocalSection) {
  if (!selectedSongId.value) { ElMessage.warning('请先选择一首歌曲'); return }
  editingSectionId.value = section?.id ?? null
  Object.assign(sectionDraft, section ? {
    title: section.title, startMarker: section.startMarker, endMarker: section.endMarker,
    focus: section.focus, sortOrder: section.sortOrder,
  } : { title: '', startMarker: '', endMarker: '', focus: '', sortOrder: sections.value.length * 10 })
  sectionDialog.value = true
}
async function saveSection() {
  if (!selectedSongId.value || !sectionDraft.title.trim()) { ElMessage.warning('请填写段落名称'); return }
  busy.value = true
  try {
    await vocalApi.saveSection(selectedSongId.value, { ...sectionDraft }, editingSectionId.value ?? undefined)
    sections.value = await vocalApi.sections(selectedSongId.value)
    sectionDialog.value = false
    ElMessage.success(editingSectionId.value ? '段落已更新' : '段落已添加')
  } catch { ElMessage.error('段落保存失败') }
  finally { busy.value = false }
}
async function removeSection(section: VocalSection) {
  try {
    await ElMessageBox.confirm('删除段落不会删除历史录音，但会清除录音和作业中的段落关联。', '删除段落', { type: 'warning' })
    await vocalApi.removeSection(section.id)
    if (selectedSectionId.value === section.id) selectedSectionId.value = null
    if (selectedSongId.value) sections.value = await vocalApi.sections(selectedSongId.value)
    await refreshAssignments()
    ElMessage.success('段落已删除')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error('删除段落失败')
  }
}

function openLesson(lesson?: VocalLesson) {
  editingLessonId.value = lesson?.id ?? null
  Object.assign(lessonDraft, lesson ? {
    lessonDate: lesson.lessonDate, teacherName: lesson.teacherName, summary: lesson.summary, feedback: lesson.feedback,
  } : { lessonDate: localToday(), teacherName: '', summary: '', feedback: '' })
  lessonDialog.value = true
}
async function saveLesson() {
  if (!lessonDraft.lessonDate) { ElMessage.warning('请填写上课日期'); return }
  busy.value = true
  try {
    await vocalApi.saveLesson({ ...lessonDraft }, editingLessonId.value ?? undefined)
    await refreshLessons()
    lessonDialog.value = false
    ElMessage.success(editingLessonId.value ? '课程记录已更新' : '课程记录已保存')
  } catch { ElMessage.error('课程记录保存失败') }
  finally { busy.value = false }
}
async function removeLesson(lesson: VocalLesson) {
  try {
    await ElMessageBox.confirm('删除课程记录不会删除课后作业，作业将变为未关联课程。', '删除课程记录', { type: 'warning' })
    await vocalApi.removeLesson(lesson.id)
    await Promise.all([refreshLessons(), refreshAssignments()])
    ElMessage.success('课程记录已删除')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error('删除课程记录失败')
  }
}

function openAssignment(assignment?: VocalAssignment) {
  editingAssignmentId.value = assignment?.id ?? null
  Object.assign(assignmentDraft, assignment ? {
    lessonId: assignment.lessonId, songId: assignment.songId, sectionId: assignment.sectionId,
    title: assignment.title, detail: assignment.detail, dueDate: assignment.dueDate, status: assignment.status,
  } : {
    lessonId: null, songId: selectedSongId.value, sectionId: selectedSectionId.value,
    title: '', detail: '', dueDate: null, status: 'TODO',
  })
  assignmentDialog.value = true
}
async function saveAssignment() {
  if (!assignmentDraft.title.trim()) { ElMessage.warning('请填写课后作业名称'); return }
  if (assignmentDraft.sectionId && !assignmentDraft.songId) { ElMessage.warning('选择段落时必须关联所属歌曲'); return }
  busy.value = true
  try {
    await vocalApi.saveAssignment({ ...assignmentDraft }, editingAssignmentId.value ?? undefined)
    await Promise.all([refreshAssignments(), refreshLessons()])
    assignmentDialog.value = false
    ElMessage.success(editingAssignmentId.value ? '课后作业已更新' : '课后作业已创建')
  } catch { ElMessage.error('课后作业保存失败，请检查课程与歌曲关联') }
  finally { busy.value = false }
}
async function cycleAssignment(assignment: VocalAssignment) {
  const status: VocalAssignment['status'] = assignment.status === 'TODO' ? 'IN_PROGRESS' : 'DONE'
  try {
    await vocalApi.saveAssignment({
      lessonId: assignment.lessonId, songId: assignment.songId, sectionId: assignment.sectionId,
      title: assignment.title, detail: assignment.detail, dueDate: assignment.dueDate, status,
    }, assignment.id)
    await Promise.all([refreshAssignments(), refreshLessons()])
  } catch { ElMessage.error('作业状态更新失败') }
}
async function removeAssignment(assignment: VocalAssignment) {
  try {
    await ElMessageBox.confirm('确定删除这条课后作业吗？', '删除课后作业', { type: 'warning' })
    await vocalApi.removeAssignment(assignment.id)
    await Promise.all([refreshAssignments(), refreshLessons()])
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error('删除课后作业失败')
  }
}
</script>

<template>
  <section class="vocal-library" v-loading="busy">
    <article class="vocal-library-panel">
      <div class="library-heading">
        <div>
          <p class="section-kicker">SONG LIBRARY</p>
          <h2><el-icon><Headset /></el-icon> 我的曲目与练习段落</h2>
        </div>
        <el-button type="primary" :icon="Plus" @click="openSong()">添加曲目</el-button>
      </div>
      <p class="library-description">保存你正在学习的歌曲，把副歌、主歌或高音句拆成段落；录音可以关联到具体段落，方便之后反复对比。</p>

      <div class="record-association">
        <div class="association-label">
          <el-icon><Collection /></el-icon>
          <div><strong>本次录音关联</strong><small>在这里选择歌曲和段落，结束录音后会随录音一起保存。</small></div>
        </div>
        <el-select v-model="selectedSongId" clearable placeholder="不关联歌曲" class="association-select">
          <el-option v-for="song in songs" :key="song.id" :label="song.title + (song.artist ? ' · ' + song.artist : '')" :value="song.id" />
        </el-select>
        <el-select v-model="selectedSectionId" clearable :disabled="!selectedSongId || !sections.length"
          placeholder="可选：关联具体段落" class="association-select">
          <el-option v-for="section in sections" :key="section.id" :label="section.title" :value="section.id" />
        </el-select>
      </div>

      <div v-if="songs.length" class="song-library-list">
        <div v-for="song in songs" :key="song.id" class="library-song-row" :class="{ 'is-active': selectedSongId === song.id }">
          <div class="library-song-art"><el-icon><Headset /></el-icon></div>
          <div class="library-song-copy">
            <strong>{{ song.title }}</strong>
            <span>{{ song.artist || '未填写歌手' }}<template v-if="song.originalKey"> · 原调 {{ song.originalKey }}</template></span>
            <small>{{ song.sectionCount }} 个练习段落<template v-if="song.note"> · {{ song.note }}</template></small>
          </div>
          <el-tag size="small" :type="song.status === 'MASTERED' ? 'success' : song.status === 'PLANNED' ? 'info' : 'warning'">{{ songStatus(song.status) }}</el-tag>
          <div class="library-song-actions">
            <el-button text size="small" @click="manageSections(song)">段落</el-button>
            <el-button text size="small" :icon="EditPen" @click="openSong(song)" aria-label="编辑歌曲" />
            <el-button text type="danger" size="small" :icon="Delete" @click="removeSong(song)" aria-label="删除歌曲" />
          </div>
        </div>
      </div>
      <el-empty v-else :image-size="52" description="曲库还是空的，先添加一首正在练习的歌曲" />

      <div id="vocal-section-editor" class="section-editor">
        <div class="subsection-heading">
          <div><h3>歌曲段落</h3><p>{{ songs.find(song => song.id === selectedSongId)?.title || '先选择一首歌曲' }}</p></div>
          <el-button size="small" :icon="Plus" :disabled="!selectedSongId" @click="openSection()">添加段落</el-button>
        </div>
        <div v-if="sections.length" class="section-list">
          <div v-for="section in sections" :key="section.id" class="section-row">
            <div class="section-row-copy">
              <strong>{{ section.title }}</strong>
              <span v-if="section.startMarker || section.endMarker">{{ section.startMarker || '起点未记'} } → {{ section.endMarker || '终点未记' }}</span>
              <small>{{ section.focus || '尚未填写练习重点' }}</small>
            </div>
            <el-button text size="small" @click="selectedSectionId = section.id">用于录音</el-button>
            <el-button text size="small" :icon="EditPen" @click="openSection(section)" aria-label="编辑段落" />
            <el-button text type="danger" size="small" :icon="Delete" @click="removeSection(section)" aria-label="删除段落" />
          </div>
        </div>
        <p v-else class="empty-hint">可按主歌、副歌、桥段或具体难句建立段落，不需要填写精确时间点。</p>
      </div>

      <el-dialog v-model="songDialog" :title="editingSongId ? '编辑曲目' : '添加曲目'" width="min(520px, 94vw)" destroy-on-close>
        <el-form label-position="top">
          <el-form-item label="歌曲名称" required><el-input v-model="songDraft.title" maxlength="120" placeholder="例如：可惜没如果" /></el-form-item>
          <el-form-item label="歌手"><el-input v-model="songDraft.artist" maxlength="120" placeholder="原唱或主要演唱者" /></el-form-item>
          <el-form-item label="原调（可选）"><el-input v-model="songDraft.originalKey" maxlength="20" placeholder="例如：A 调、C# 调" /></el-form-item>
          <el-form-item label="学习状态">
            <el-select v-model="songDraft.status" class="full-width">
              <el-option label="待练习" value="PLANNED" /><el-option label="练习中" value="LEARNING" /><el-option label="基本掌握" value="MASTERED" />
            </el-select>
          </el-form-item>
          <el-form-item label="练习备注"><el-input v-model="songDraft.note" type="textarea" maxlength="500" :rows="2" /></el-form-item>
        </el-form>
        <template #footer><el-button @click="songDialog = false">取消</el-button><el-button type="primary" @click="saveSong">保存曲目</el-button></template>
      </el-dialog>
      <el-dialog v-model="sectionDialog" :title="editingSectionId ? '编辑段落' : '添加练习段落'" width="min(520px, 94vw)" destroy-on-close>
        <el-form label-position="top">
          <el-form-item label="段落名称" required><el-input v-model="sectionDraft.title" maxlength="120" placeholder="例如：副歌第一句、高音长音" /></el-form-item>
          <div class="marker-grid">
            <el-form-item label="起始位置（可选）"><el-input v-model="sectionDraft.startMarker" maxlength="40" placeholder="例如：01:20" /></el-form-item>
            <el-form-item label="结束位置（可选）"><el-input v-model="sectionDraft.endMarker" maxlength="40" placeholder="例如：01:48" /></el-form-item>
          </div>
          <el-form-item label="练习重点"><el-input v-model="sectionDraft.focus" type="textarea" maxlength="500" :rows="3" placeholder="例如：换气位置、音高衔接、咬字和情绪" /></el-form-item>
          <el-form-item label="排序"><el-input-number v-model="sectionDraft.sortOrder" :min="0" :max="9999" /></el-form-item>
        </el-form>
        <template #footer><el-button @click="sectionDialog = false">取消</el-button><el-button type="primary" @click="saveSection">保存段落</el-button></template>
      </el-dialog>
    </article>

    <article class="vocal-library-panel">
      <div class="library-heading">
        <div><p class="section-kicker">LESSONS & HOMEWORK</p><h2><el-icon><Calendar /></el-icon> 课程记录与课后作业</h2></div>
        <el-button type="primary" plain :icon="Plus" @click="openLesson()">记录课程</el-button>
      </div>
      <p class="library-description">记录老师讲解、反馈与课后任务，并把任务关联到歌曲段落。作业状态可逐步更新，删除课程不会连带删除作业。</p>

      <div class="lesson-list">
        <div v-for="lesson in lessons.slice(0, 4)" :key="lesson.id" class="lesson-row">
          <div class="lesson-date"><strong>{{ lesson.lessonDate.slice(5).replace('-', '/') }}</strong><small>{{ lesson.teacherName || '自主复盘' }}</small></div>
          <div class="lesson-copy"><strong>{{ lesson.summary || '课程记录' }}</strong><span>{{ lesson.feedback || '尚未填写老师反馈' }}</span><small>{{ lesson.assignmentCount }} 条关联作业</small></div>
          <div class="lesson-actions">
            <el-button text size="small" :icon="EditPen" @click="openLesson(lesson)" aria-label="编辑课程" />
            <el-button text type="danger" size="small" :icon="Delete" @click="removeLesson(lesson)" aria-label="删除课程" />
          </div>
        </div>
        <p v-if="!lessons.length" class="empty-hint">还没有课程记录；也可以先记录一次自我复盘。</p>
      </div>

      <div class="subsection-heading assignment-heading">
        <div><h3>课后作业</h3><p>{{ assignments.filter(a => a.status !== 'DONE').length }} 条待完成</p></div>
        <el-button size="small" :icon="Plus" @click="openAssignment()">添加作业</el-button>
      </div>
      <div v-if="assignments.length" class="assignment-list">
        <div v-for="assignment in assignments.slice(0, 8)" :key="assignment.id" class="assignment-row">
          <div class="assignment-check" :class="{ done: assignment.status === 'DONE' }">
            <el-icon><Check /></el-icon>
          </div>
          <div class="assignment-copy">
            <strong :class="{ 'is-done': assignment.status === 'DONE' }">{{ assignment.title }}</strong>
            <span v-if="assignment.songTitle">{{ assignment.songTitle }}<template v-if="assignment.sectionTitle"> · {{ assignment.sectionTitle }}</template></span>
            <small>{{ assignment.dueDate ? '截止 ' + assignment.dueDate : '未设置截止日期' }}<template v-if="assignment.detail"> · {{ assignment.detail }}</template></small>
          </div>
          <el-tag size="small" :type="assignmentTag(assignment.status)">{{ assignmentStatus(assignment.status) }}</el-tag>
          <div class="assignment-actions">
            <el-button v-if="assignment.status !== 'DONE'" text size="small" @click="cycleAssignment(assignment)">推进</el-button>
            <el-button text size="small" :icon="EditPen" @click="openAssignment(assignment)" aria-label="编辑作业" />
            <el-button text type="danger" size="small" :icon="Delete" @click="removeAssignment(assignment)" aria-label="删除作业" />
          </div>
        </div>
      </div>
      <p v-else class="empty-hint">课程结束后，把老师布置的内容转成可追踪的练习任务。</p>

      <el-dialog v-model="lessonDialog" :title="editingLessonId ? '编辑课程记录' : '记录一节课'" width="min(560px, 94vw)" destroy-on-close>
        <el-form label-position="top">
          <el-form-item label="上课日期" required><el-date-picker v-model="lessonDraft.lessonDate" type="date" value-format="YYYY-MM-DD" class="full-width" /></el-form-item>
          <el-form-item label="老师 / 课程来源"><el-input v-model="lessonDraft.teacherName" maxlength="120" placeholder="老师姓名或自主练习" /></el-form-item>
          <el-form-item label="本节课内容"><el-input v-model="lessonDraft.summary" type="textarea" maxlength="4000" :rows="3" placeholder="练习内容、发声方法、课堂重点" /></el-form-item>
          <el-form-item label="老师反馈 / 自我复盘"><el-input v-model="lessonDraft.feedback" type="textarea" maxlength="4000" :rows="3" placeholder="需要改进的地方、下次上课要确认的问题" /></el-form-item>
        </el-form>
        <template #footer><el-button @click="lessonDialog = false">取消</el-button><el-button type="primary" @click="saveLesson">保存课程</el-button></template>
      </el-dialog>
      <el-dialog v-model="assignmentDialog" :title="editingAssignmentId ? '编辑课后作业' : '添加课后作业'" width="min(560px, 94vw)" destroy-on-close>
        <el-form label-position="top">
          <el-form-item label="作业名称" required><el-input v-model="assignmentDraft.title" maxlength="160" placeholder="例如：副歌高音句慢速模唱 5 次" /></el-form-item>
          <el-form-item label="关联课程">
            <el-select v-model="assignmentDraft.lessonId" clearable class="full-width" placeholder="可选">
              <el-option v-for="lesson in lessons" :key="lesson.id" :label="lesson.lessonDate + ' · ' + (lesson.teacherName || '自主复盘')" :value="lesson.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="关联歌曲">
            <el-select v-model="assignmentDraft.songId" clearable class="full-width" placeholder="可选">
              <el-option v-for="song in songs" :key="song.id" :label="song.title" :value="song.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="关联段落">
            <el-select v-model="assignmentDraft.sectionId" clearable :disabled="!assignmentDraft.songId" class="full-width" placeholder="可选">
              <el-option v-for="section in assignmentSections" :key="section.id" :label="section.title" :value="section.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="截止日期"><el-date-picker v-model="assignmentDraft.dueDate" clearable type="date" value-format="YYYY-MM-DD" class="full-width" /></el-form-item>
          <el-form-item label="练习要求"><el-input v-model="assignmentDraft.detail" type="textarea" maxlength="4000" :rows="3" /></el-form-item>
          <el-form-item label="状态">
            <el-select v-model="assignmentDraft.status" class="full-width">
              <el-option label="待练习" value="TODO" /><el-option label="进行中" value="IN_PROGRESS" /><el-option label="已完成" value="DONE" />
            </el-select>
          </el-form-item>
        </el-form>
        <template #footer><el-button @click="assignmentDialog = false">取消</el-button><el-button type="primary" @click="saveAssignment">保存作业</el-button></template>
      </el-dialog>
    </article>
  </section>
</template>

<style scoped>
.vocal-library{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;margin:16px 0;align-items:start}
.vocal-library-panel{min-width:0;border:1px solid var(--el-border-color-lighter);border-radius:18px;padding:20px;background:var(--el-bg-color)}
.library-heading{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:8px}
.library-heading h2{display:flex;align-items:center;gap:8px;font-size:18px;margin:4px 0 0}
.library-heading h2 .el-icon{color:var(--el-color-primary)}
.section-kicker{margin:0;font-size:10px;letter-spacing:1.6px;font-weight:700;color:var(--el-color-primary)}
.library-description{font-size:12px;line-height:1.65;color:var(--el-text-color-secondary);margin:10px 0 15px}
.record-association{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:12px;border-radius:12px;background:var(--el-fill-color-lighter);margin-bottom:14px}
.association-label{grid-column:1/-1;display:flex;gap:9px;align-items:center}
.association-label>.el-icon{font-size:20px;color:var(--el-color-primary)}
.association-label strong,.association-label small{display:block}
.association-label strong{font-size:12px}
.association-label small{font-size:10px;line-height:1.5;color:var(--el-text-color-secondary);margin-top:3px}
.association-select{width:100%;min-width:0}
.song-library-list,.lesson-list,.assignment-list,.section-list{display:grid;gap:8px}
.library-song-row{display:flex;align-items:center;gap:9px;padding:10px;border:1px solid var(--el-border-color-lighter);border-radius:12px;min-width:0}
.library-song-row.is-active{border-color:var(--el-color-primary);background:var(--el-color-primary-light-9)}
.library-song-art{width:35px;height:35px;display:grid;place-items:center;flex-shrink:0;border-radius:10px;background:var(--el-fill-color-light);color:var(--el-color-primary);font-size:18px}
.library-song-copy{min-width:0;flex:1}
.library-song-copy strong,.library-song-copy span,.library-song-copy small{display:block;overflow-wrap:anywhere}
.library-song-copy strong{font-size:13px}
.library-song-copy span,.library-song-copy small{font-size:10px;color:var(--el-text-color-secondary);line-height:1.5;margin-top:3px}
.library-song-actions{display:flex;align-items:center;gap:0;flex-shrink:0}
.section-editor{border-top:1px solid var(--el-border-color-lighter);margin-top:16px;padding-top:14px}
.subsection-heading{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:10px}
.subsection-heading h3{font-size:14px;margin:0}
.subsection-heading p{font-size:10px;color:var(--el-text-color-secondary);margin:4px 0 0}
.section-row{display:flex;align-items:center;gap:4px;border:1px solid var(--el-border-color-lighter);border-radius:10px;padding:9px;min-width:0}
.section-row-copy{min-width:0;flex:1}
.section-row-copy strong,.section-row-copy span,.section-row-copy small{display:block;overflow-wrap:anywhere}
.section-row-copy strong{font-size:12px}
.section-row-copy span,.section-row-copy small{font-size:10px;line-height:1.5;color:var(--el-text-color-secondary);margin-top:3px}
.empty-hint{font-size:11px;line-height:1.6;color:var(--el-text-color-secondary);padding:12px;background:var(--el-fill-color-lighter);border-radius:10px}
.full-width{width:100%}
.marker-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.lesson-row{display:flex;align-items:start;gap:10px;border:1px solid var(--el-border-color-lighter);border-radius:11px;padding:10px;min-width:0}
.lesson-date{width:55px;flex-shrink:0}
.lesson-date strong,.lesson-date small{display:block}
.lesson-date strong{font-size:13px}
.lesson-date small{font-size:10px;color:var(--el-text-color-secondary);margin-top:4px;overflow-wrap:anywhere}
.lesson-copy{min-width:0;flex:1}
.lesson-copy strong,.lesson-copy span,.lesson-copy small{display:block;overflow-wrap:anywhere}
.lesson-copy strong{font-size:12px}
.lesson-copy span,.lesson-copy small{font-size:10px;line-height:1.5;color:var(--el-text-color-secondary);margin-top:4px}
.lesson-actions{display:flex;gap:0;flex-shrink:0}
.assignment-heading{border-top:1px solid var(--el-border-color-lighter);margin-top:16px;padding-top:14px}
.assignment-row{display:flex;align-items:center;gap:8px;border:1px solid var(--el-border-color-lighter);border-radius:11px;padding:9px;min-width:0}
.assignment-check{width:23px;height:23px;display:grid;place-items:center;border:1px solid var(--el-border-color);border-radius:50%;color:transparent;flex-shrink:0}
.assignment-check.done{background:var(--el-color-success-light-8);border-color:var(--el-color-success);color:var(--el-color-success)}
.assignment-copy{min-width:0;flex:1}
.assignment-copy strong,.assignment-copy span,.assignment-copy small{display:block;overflow-wrap:anywhere}
.assignment-copy strong{font-size:12px}
.assignment-copy strong.is-done{text-decoration:line-through;color:var(--el-text-color-secondary)}
.assignment-copy span,.assignment-copy small{font-size:10px;line-height:1.5;color:var(--el-text-color-secondary);margin-top:3px}
.assignment-actions{display:flex;align-items:center;gap:0;flex-shrink:0}
@media(max-width:1000px){.vocal-library{grid-template-columns:1fr}}
@media(max-width:520px){.vocal-library-panel{padding:14px}.record-association{grid-template-columns:1fr}.association-label{grid-column:auto}.library-song-row{flex-wrap:wrap}.library-song-actions{margin-left:auto}.library-song-row>.el-tag{margin-left:auto}.section-row{flex-wrap:wrap}.section-row-copy{flex-basis:100%}.assignment-row{flex-wrap:wrap}.assignment-copy{min-width:calc(100% - 35px)}.assignment-actions{margin-left:auto}.marker-grid{grid-template-columns:1fr}}
</style>
