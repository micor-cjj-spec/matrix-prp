<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '@/layouts/AppLayout.vue'
import * as api from '@/api/practice'
import type { Subject, Bank, Question, QuestionForm, PlayQuestion, GradeResult, Statistics } from '@/api/practice'

const busy = ref(false)
const subjects = ref<Subject[]>([])
const banks = ref<Bank[]>([])
const questions = ref<Question[]>([])
const subjectId = ref<number|null>(null)
const bankId = ref<number|null>(null)
const subjectName = ref('')
const bankName = ref('')
const sourceName = ref('')
const tab = ref('questions')
const draft = ref<QuestionForm>(blank())
const editId = ref<number|null>(null)
const answerInput = ref('A')
const importFormat = ref<'json'|'csv'>('json')
const importContent = ref('')
const importSource = ref('')
const previewCount = ref<number|null>(null)
const aiTopic = ref('')
const aiCount = ref(3)
const aiDifficulty = ref('medium')
const playable = ref<PlayQuestion[]>([])
const playIndex = ref(0)
const selected = ref<string[]>([])
const result = ref<GradeResult|null>(null)
const followup = ref('')
const explanation = ref('')
const stats = ref<Statistics>({attempted:0,correct:0,wrong:0})
const bank = computed(() => banks.value.find(v => v.id === bankId.value))
const active = computed(() => playable.value[playIndex.value] ?? null)

function blank():QuestionForm {
  return {type:'single',stem:'',options:['A','B','C','D'].map(key=>({key,text:''})),answers:['A'],explanation:'',difficulty:'medium'}
}
function getError(e:unknown):string {
  if (typeof e === 'object' && e !== null && 'response' in e) {
    const response = (e as {response?:{data?:{message?:string}}}).response
    if (response?.data?.message) return response.data.message
  }
  return e instanceof Error ? e.message : '请求失败'
}
async function execute<T>(job:()=>Promise<T>, success=''):Promise<T|undefined> {
  busy.value = true
  try { const value = await job(); if (success) ElMessage.success(success); return value }
  catch(e) { ElMessage.error(getError(e)); return undefined }
  finally { busy.value = false }
}
async function refreshSubjects() { const rows = await execute(api.getSubjects); if(rows) subjects.value = rows }
async function chooseSubject(id:number|null) {
  subjectId.value = id; bankId.value = null; banks.value = []; questions.value = []; playable.value = []
  if (id != null) { const rows = await execute(()=>api.getBanks(id)); if(rows) banks.value = rows }
}
async function refreshBanks() {
  if(subjectId.value == null) return
  const rows = await execute(()=>api.getBanks(subjectId.value!)); if(rows) banks.value = rows
}
async function chooseBank(id:number|null) {
  bankId.value = id; questions.value = []; playable.value = []; result.value = null
  if(id != null) await refreshQuestions()
}
async function refreshQuestions() {
  if(bankId.value == null) return
  const rows = await execute(()=>api.getQuestions(bankId.value!)); if(rows) questions.value = rows
}
async function createSubject() {
  const s = await execute(()=>api.addSubject({name:subjectName.value,parentId:null,description:''}),'学科创建成功')
  if(s) { subjectName.value=''; await refreshSubjects(); await chooseSubject(s.id) }
}
async function modifySubject(s:Subject) {
  try {
    const v = await ElMessageBox.prompt('学科名称','编辑学科',{inputValue:s.name,inputPattern:/\S+/})
    await execute(async()=>{await api.editSubject(s.id,{parentId:s.parentId,name:v.value,description:s.description});await refreshSubjects()},'保存成功')
  } catch { /* cancelled */ }
}
async function removeSubject(s:Subject) {
  try {
    await ElMessageBox.confirm('只能删除没有子学科或题库的学科','确认删除')
    await execute(async()=>{await api.removeSubject(s.id);await refreshSubjects();if(subjectId.value===s.id)await chooseSubject(null)},'学科已删除')
  } catch { /* cancelled */ }
}
async function createBank() {
  if(subjectId.value == null)return
  const b = await execute(()=>api.addBank({subjectId:subjectId.value!,title:bankName.value,description:'',sourceName:sourceName.value,licenseNote:''}),'题库创建成功')
  if(b){bankName.value='';sourceName.value='';await refreshBanks();await chooseBank(b.id)}
}
async function modifyBank(b:Bank) {
  try{
    const v = await ElMessageBox.prompt('题库名称','编辑题库',{inputValue:b.title,inputPattern:/\S+/})
    await execute(async()=>{await api.editBank(b.id,{subjectId:b.subjectId,title:v.value,description:b.description,sourceName:b.sourceName,licenseNote:b.licenseNote});await refreshBanks()},'保存成功')
  }catch{ /* cancelled */ }
}
async function removeBank(b:Bank){
  try{
    await ElMessageBox.confirm('只能删除没有题目的题库','确认删除')
    await execute(async()=>{await api.removeBank(b.id);await refreshBanks();if(bankId.value===b.id)await chooseBank(null)},'题库已删除')
  }catch{ /* cancelled */ }
}
async function toggleBank(b:Bank){
  await execute(async()=>{await api.setBankStatus(b.id,b.status==='draft'?'published':'draft');await refreshBanks()},'已更新题库状态')
}
async function saveQuestion() {
  if(bankId.value===null)return
  const value:QuestionForm = {...draft.value,
    options:draft.value.options.filter(o=>o.text.trim().length>0),
    answers:answerInput.value.toUpperCase().split(/[,，| ]+/).filter(Boolean)}
  const success=await execute(async()=>{
    if(editId.value!==null)await api.editQuestion(editId.value,value)
    else await api.addQuestion(bankId.value!,value)
    return true
  },'题目草稿已保存')
  if(success){draft.value=blank();answerInput.value='A';editId.value=null;await refreshQuestions();tab.value='questions'}
}
function openQuestion(q:Question){
  editId.value=q.id;draft.value={type:q.type,stem:q.stem,options:q.options.map(o=>({...o})),answers:[...q.answers],explanation:q.explanation,difficulty:q.difficulty}
  answerInput.value=q.answers.join(',');tab.value='editor'
}
async function toggleQuestion(q:Question){
  await execute(async()=>{await api.setQuestionStatus(q.id,q.status==='draft'?'published':'draft');await refreshQuestions()},'题目状态已更新')
}
async function removeQuestion(q:Question){
  try{
    await ElMessageBox.confirm('有答题历史的题目不可删除，可以撤回发布','确认删除')
    await execute(async()=>{await api.removeQuestion(q.id);await refreshQuestions()},'题目已删除')
  }catch{ /* cancelled */ }
}
async function fileChanged(event:Event){
  const file=(event.target as HTMLInputElement).files?.[0]
  if(!file)return
  if(file.size>1000000){ElMessage.warning('文件不能超过 1MB');return}
  importFormat.value=file.name.endsWith('.csv')?'csv':'json'
  importContent.value=await file.text()
  importSource.value=file.name
  previewCount.value=null
}
async function previewImport(){
  const data=await execute(()=>api.previewImport({format:importFormat.value,content:importContent.value,sourceName:importSource.value}))
  if(data)previewCount.value=data.total
}
async function doImport(){
  if(bankId.value==null||previewCount.value===null)return
  const r=await execute(()=>api.importQuestions(bankId.value!,{format:importFormat.value,content:importContent.value,sourceName:importSource.value}))
  if(r){ElMessage.success('导入 '+r.imported+' 道草稿；跳过 '+r.duplicates+' 道重复题');previewCount.value=null;await refreshQuestions();tab.value='questions'}
}
async function generate(){
  if(bankId.value==null)return
  const r=await execute(()=>api.generateQuestions(bankId.value!,aiTopic.value,aiDifficulty.value,aiCount.value))
  if(r){ElMessage.success('生成 '+r.imported+' 道草稿，请审核后发布');await refreshQuestions();tab.value='questions'}
}
async function startPractice(wrong=false){
  if(bankId.value==null&&!wrong)return
  const rows=await execute(()=>wrong?api.getWrongQuestions():api.getPlayQuestions(bankId.value!))
  if(rows){playable.value=rows;playIndex.value=0;selected.value=[];result.value=null;explanation.value='';tab.value='practice';if(!rows.length)ElMessage.info('暂无可练习题目')}
}
async function check(){
  if(!active.value)return
  const r=await execute(()=>api.submitAnswer(active.value!.id,selected.value))
  if(r){result.value=r;const s=await execute(api.getStatistics);if(s)stats.value=s}
}
function next(){
  playIndex.value+=1;selected.value=[];result.value=null;followup.value='';explanation.value=''
}
async function askAi(){
  if(!active.value)return
  const r=await execute(()=>api.explainQuestion(active.value!.id,followup.value))
  if(r)explanation.value=r.content
}
onMounted(async()=>{await refreshSubjects();const s=await execute(api.getStatistics);if(s)stats.value=s})
</script>

<template>
  <AppLayout>
    <header class="page-header"><div>
      <p class="eyebrow">Matrix Practice</p>
      <h1>智能刷题中心</h1>
      <p>自由创建学科与题库，导入或 AI 生成题目，练习与解答。</p>
    </div></header>
    <el-row :gutter="12" style="margin-bottom:16px">
      <el-col :xs="24" :sm="8"><el-card shadow="never">累计答题：{{stats.attempted}}</el-card></el-col>
      <el-col :xs="24" :sm="8"><el-card shadow="never">答对：{{stats.correct}}</el-card></el-col>
      <el-col :xs="24" :sm="8"><el-card shadow="never">答错：{{stats.wrong}}</el-card></el-col>
    </el-row>
    <div class="practice-grid">
      <el-card shadow="never">
        <template #header><strong>我的学科</strong></template>
        <el-input v-model="subjectName" maxlength="120" placeholder="例如：Java、英语、软考" />
        <el-button type="primary" style="margin:10px 0" :loading="busy" @click="createSubject">+ 创建学科</el-button>
        <div v-for="s in subjects" :key="s.id" class="practice-row">
          <el-button link :type="subjectId===s.id?'primary':'default'" @click="chooseSubject(s.id)">{{s.name}}</el-button>
          <span><el-button link @click="modifySubject(s)">编辑</el-button><el-button link type="danger" @click="removeSubject(s)">删除</el-button></span>
        </div>
      </el-card>
      <el-card shadow="never">
        <template #header><strong>当前学科的题库</strong></template>
        <el-empty v-if="subjectId===null" description="请先选择学科"/>
        <template v-else>
          <el-input v-model="bankName" placeholder="题库名称" maxlength="160"/>
          <el-input v-model="sourceName" placeholder="来源说明（选填）" style="margin-top:8px"/>
          <el-button type="primary" plain style="margin:10px 0" :loading="busy" @click="createBank">+ 创建题库</el-button>
          <el-empty v-if="!banks.length" description="尚无题库"/>
          <div v-for="b in banks" :key="b.id" class="practice-row">
            <div><el-button link :type="bankId===b.id?'primary':'default'" @click="chooseBank(b.id)">{{b.title}}</el-button><el-tag size="small" :type="b.status==='published'?'success':'info'">{{b.status==='published'?'已发布':'草稿'}}</el-tag></div>
            <div><el-button link @click="modifyBank(b)">编辑</el-button><el-button link @click="toggleBank(b)">{{b.status==='draft'?'发布':'撤回'}}</el-button><el-button link type="danger" @click="removeBank(b)">删除</el-button></div>
          </div>
        </template>
      </el-card>
    </div>

    <el-card v-if="bankId!==null" shadow="never" style="margin-top:16px">
      <template #header><div class="practice-row"><strong>{{bank?.title}} · 题目管理</strong><el-button type="primary" @click="startPractice()">开始练习</el-button></div></template>
      <el-tabs v-model="tab">
        <el-tab-pane label="题目列表" name="questions">
          <el-empty v-if="!questions.length" description="暂无题目：可以手工录入、文件导入或 AI 生成"/>
          <div v-for="(q,i) in questions" :key="q.id" class="practice-row">
            <div><strong>{{i+1}}. {{q.stem}}</strong><p class="practice-muted">{{q.type}} · {{q.difficulty}} · {{q.status==='published'?'已发布':'草稿'}}</p></div>
            <div><el-button size="small" :disabled="q.status==='published'" @click="openQuestion(q)">编辑</el-button>
              <el-button size="small" @click="toggleQuestion(q)">{{q.status==='draft'?'发布':'撤回'}}</el-button>
              <el-button size="small" type="danger" plain @click="removeQuestion(q)">删除</el-button></div>
          </div>
        </el-tab-pane>
        <el-tab-pane label="手工录题" name="editor">
          <el-form label-position="top" @submit.prevent>
            <el-form-item label="题目"><el-input v-model="draft.stem" type="textarea" :rows="3"/></el-form-item>
            <el-form-item label="题型"><el-select v-model="draft.type"><el-option value="single" label="单选"/><el-option value="multiple" label="多选"/><el-option value="boolean" label="判断"/></el-select></el-form-item>
            <el-form-item label="难度"><el-select v-model="draft.difficulty"><el-option value="easy" label="简单"/><el-option value="medium" label="中等"/><el-option value="hard" label="困难"/></el-select></el-form-item>
            <el-form-item v-for="o in draft.options" :key="o.key" :label="'选项 '+o.key"><el-input v-model="o.text"/></el-form-item>
            <el-form-item label="正确答案（多选用逗号分隔）"><el-input v-model="answerInput" placeholder="A 或 A,C"/></el-form-item>
            <el-form-item label="参考解析"><el-input v-model="draft.explanation" type="textarea" :rows="3"/></el-form-item>
            <el-button type="primary" :loading="busy" @click="saveQuestion">保存草稿</el-button>
            <el-button @click="draft=blank();editId=null;answerInput='A'">重置</el-button>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="JSON / CSV 导入" name="import">
          <p class="practice-muted">单次最多 200 题、1MB；导入之前预览校验。所有题目先进入草稿。</p>
          <input type="file" accept=".json,.csv" @change="fileChanged"/>
          <el-input v-model="importContent" type="textarea" :rows="5" placeholder="也可以粘贴题目 JSON 数组或 CSV" style="margin-top:12px" @input="previewCount=null"/>
          <el-radio-group v-model="importFormat" style="margin:10px 0"><el-radio value="json">JSON</el-radio><el-radio value="csv">CSV</el-radio></el-radio-group>
          <div><el-button :loading="busy" @click="previewImport">预览校验</el-button><el-button type="primary" :loading="busy" :disabled="previewCount===null" @click="doImport">确认导入</el-button></div>
          <p v-if="previewCount!==null" class="practice-muted">校验通过 {{previewCount}} 道题</p>
        </el-tab-pane>
        <el-tab-pane label="AI 生成题目" name="ai">
          <el-alert title="AI 生成结果仅为草稿，需要人工审核；后端需配置 DeepSeek Key，每个用户每天限 20 次。" type="info" :closable="false" show-icon/>
          <el-form label-position="top" style="margin-top:15px" @submit.prevent>
            <el-form-item label="知识点与出题要求"><el-input v-model="aiTopic" maxlength="400" type="textarea" :rows="3" placeholder="例如：Spring Boot 自动配置原理"/></el-form-item>
            <el-form-item label="难度"><el-select v-model="aiDifficulty"><el-option value="easy" label="简单"/><el-option value="medium" label="中等"/><el-option value="hard" label="困难"/></el-select></el-form-item>
            <el-form-item label="题数（1-5）"><el-input-number v-model="aiCount" :min="1" :max="5"/></el-form-item>
            <el-button type="primary" :loading="busy" :disabled="!aiTopic.trim()" @click="generate">AI 生成草稿</el-button>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="刷题 / AI 解释" name="practice">
          <div><el-button @click="startPractice()">本库练习</el-button><el-button @click="startPractice(true)">错题重练</el-button></div>
          <el-empty v-if="!playable.length" description="先发布题库与题目，再点击开始练习"/>
          <div v-else-if="active">
            <p class="practice-muted">第 {{playIndex+1}} / {{playable.length}} 题</p>
            <h3>{{active.stem}}</h3>
            <el-checkbox-group v-if="active.type==='multiple'" v-model="selected" :disabled="result!==null">
              <div v-for="o in active.options" :key="o.key"><el-checkbox :value="o.key">{{o.key}}. {{o.text}}</el-checkbox></div>
            </el-checkbox-group>
            <el-radio-group v-else :model-value="selected[0]??''" :disabled="result!==null" @update:model-value="selected=[String($event)]">
              <div v-for="o in active.options" :key="o.key"><el-radio :value="o.key">{{o.key}}. {{o.text}}</el-radio></div>
            </el-radio-group>
            <div style="margin-top:16px">
              <el-button v-if="!result" type="primary" :disabled="selected.length===0" :loading="busy" @click="check">提交答案</el-button>
              <el-button v-else-if="playIndex<playable.length-1" type="primary" @click="next">下一题</el-button>
              <el-tag v-if="result" :type="result.correct?'success':'danger'">{{result.correct?'正确':'错误'}}</el-tag>
            </div>
            <el-card v-if="result" shadow="never" style="margin-top:14px">
              <strong>正确答案：{{result.correctAnswers.join(', ')}}</strong>
              <p>{{result.explanation||'暂无人工解析'}}</p>
              <el-input v-model="followup" placeholder="为什么选这个答案？"/>
              <el-button :loading="busy" style="margin-top:10px" @click="askAi">AI 讲解与追问</el-button>
              <p v-if="explanation" class="practice-ai">{{explanation}}</p>
              <p v-if="playIndex===playable.length-1" class="practice-muted">本轮题目已完成</p>
            </el-card>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </AppLayout>
</template>

<style scoped>
.practice-grid {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.practice-row {display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;padding:10px 0;border-bottom:1px solid #edf2f7}
.practice-muted {font-size:13px;color:#64748b}
.practice-ai {white-space:pre-wrap;line-height:1.75;padding:14px;background:#f1f5f9;border-radius:8px}
@media(max-width:800px){.practice-grid{grid-template-columns:1fr}}
</style>
