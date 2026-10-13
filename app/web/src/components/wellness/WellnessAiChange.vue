<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { apiClient, type ApiResponse } from '@/api/client'
import { wellnessApi, type Meal, type Exercise, type BodyMetric } from '@/api/wellness'

type Kind = 'meal' | 'exercise' | 'metric'
type Action = 'update' | 'delete'
type Item = { foodId: number; name: string; grams: number }
type Fields = { date: string; mealType?: string; note?: string; items?: Item[];
  name?: string; durationMinutes?: number; estimatedKcal?: number | null;
  weightKg?: number; bodyFatPct?: number | null; waistCm?: number | null }
type Draft = { draftId: string; action: string; description: string; before: Fields;
  after: Fields; expiresAt: string }
type Outcome = { action: string; route: string; saved: unknown }

const props=defineProps<{ initialKind?: Kind; initialId?: number; initialDate?: string }>()
const emit=defineEmits<{ changed: [result: Outcome] }>()
const kind=ref<Kind>(props.initialKind ?? 'meal')
function localDay() {
  const d=new Date()
  return [d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),
    String(d.getDate()).padStart(2,'0')].join('-')
}
const date=ref(props.initialDate ?? localDay())
const targetId=ref(props.initialId ?? 0)
const action=ref<Action>('update')
const instruction=ref('')
const records=ref<{id: number; label: string}[]>([])
const loading=ref(false)
const busy=ref(false)
const saving=ref(false)
const draft=ref<Draft|null>(null)
const after=ref<Fields>({date:date.value})
const error=ref('')
const done=ref('')
const deleteAcknowledged=ref(false)

async function refreshRecords(){
  loading.value=true
  const currentId=targetId.value
  draft.value=null
  try {
    if (kind.value==='meal') {
      const list=await wellnessApi.meals(date.value)
      records.value=list.map((m:Meal)=>({id:m.id,label:m.mealType+' · '+m.items.map(i=>i.foodName).join('、')+' #'+m.id}))
    } else if (kind.value==='exercise') {
      const list=await wellnessApi.exercises(date.value)
      records.value=list.map((e:Exercise)=>({id:e.id,label:e.name+' · '+e.durationMinutes+'分钟 #'+e.id}))
    } else {
      const list=await wellnessApi.metrics(365)
      records.value=list.filter((m:BodyMetric)=>m.measuredOn===date.value)
        .map(m=>({id:m.id,label:m.weightKg+'kg #'+m.id}))
    }
    targetId.value=records.value.some(x=>x.id===currentId)?currentId:0
  }catch { error.value='无法读取记录，请检查网络';records.value=[] }
  finally { loading.value=false }
}
watch([kind,date],()=>{void refreshRecords()})
onMounted(()=>{void refreshRecords()})

async function prepare(){
  if(!targetId.value||busy.value)return
  busy.value=true;error.value='';done.value='';deleteAcknowledged.value=false
  try {
    const result=await apiClient.post<ApiResponse<Draft>>('/wellness/ai/changes/prepare',
      {kind:kind.value,recordId:targetId.value,operation:action.value,
        instruction:action.value==='update'?instruction.value.trim():''},
      {timeout:60000})
    draft.value=result.data.data
    after.value=structuredClone(draft.value.after)
  }catch(e){
    const err=e as {response?:{data?:{message?:string}}}
    error.value=err.response?.data?.message||'草稿生成失败，请检查模型配置和目标记录'
  }finally { busy.value=false }
}
async function confirm(){
  if(!draft.value||saving.value)return
  if(action.value==='delete'&&!deleteAcknowledged.value) {
    ElMessage.warning('请先明确勾选删除确认');return
  }
  saving.value=true;error.value=''
  try {
    if(action.value==='update'){
      await apiClient.patch('/wellness/ai/changes/'+draft.value.draftId,after.value)
    }
    const r=await apiClient.post<ApiResponse<Outcome>>('/wellness/ai/changes/'+draft.value.draftId+'/confirm',{})
    done.value=r.data.data.route
    draft.value=null
    emit('changed',r.data.data)
    await refreshRecords()
    ElMessage.success('已完成'+(action.value==='delete'?'删除':'修改'))
  }catch(e){
    const err=e as {response?:{data?:{message?:string}}}
    error.value=err.response?.data?.message||'未提交：记录可能已经修改、删除，或草稿已过期'
  }finally{saving.value=false}
}
</script>

<template>
  <section class="wellness-change">
    <strong>已有健康记录：安全修改或删除</strong>
    <small>必须先选择一条自己的记录。AI 只生成修改建议，不能直接改动或删除。</small>
    <div class="change-row">
      <label>记录日期<input v-model="date" type="date"/></label>
      <label>记录类别<select v-model="kind">
        <option value="meal">饮食</option><option value="exercise">运动</option><option value="metric">身体指标</option>
      </select></label>
    </div>
    <label>明确选择记录
      <select v-model.number="targetId" :disabled="loading">
        <option :value="0">请选择记录（不可自动猜测）</option>
        <option v-for="r in records" :key="r.id" :value="r.id">{{ r.label }}</option>
      </select>
    </label>
    <small v-if="!records.length">所选日期暂无记录</small>
    <label>操作<select v-model="action" @change="draft=null">
      <option value="update">修改</option><option value="delete">删除</option>
    </select></label>
    <label v-if="action==='update'">让 AI 修改什么？（可不填，直接编辑草稿）
      <textarea v-model="instruction" maxlength="500" rows="2"
        placeholder="例如：把这次步行改成45分钟，或午餐米饭份量改成180g"/>
    </label>
    <button :disabled="!targetId||busy||saving" @click="prepare">
      {{ busy?'处理中…':action==='delete'?'预览删除目标':'生成修改草稿' }}
    </button>
    <small>仅在填写 AI 修改说明时，会将选中记录交由当前模型解析。删除操作不会发送数据给 AI。</small>
    <p v-if="error" class="change-error" role="alert">{{ error }}</p>
    <div v-if="draft" class="change-preview">
      <strong>操作预览 · {{ draft.action }}</strong>
      <small>原始数据（只读）</small>
      <pre>{{ JSON.stringify(draft.before,null,2) }}</pre>
      <template v-if="action==='update'">
        <strong>修改后的数据（请确认）</strong>
        <label>日期<input v-model="after.date" type="date"/></label>
        <template v-if="kind==='meal'">
          <label>餐次<select v-model="after.mealType">
            <option value="BREAKFAST">早餐</option><option value="LUNCH">午餐</option>
            <option value="DINNER">晚餐</option><option value="SNACK">加餐</option>
          </select></label>
          <div v-for="(item,i) in after.items" :key="i">
            <strong>{{ item.name }}</strong>
            <label>克数<input v-model.number="item.grams" type="number" min="0.1" max="10000" step="0.1"/></label>
          </div>
          <label>备注<input v-model="after.note" maxlength="500"/></label>
        </template>
        <template v-else-if="kind==='exercise'">
          <label>名称<input v-model="after.name" maxlength="100"/></label>
          <label>时长（分钟）<input v-model.number="after.durationMinutes" type="number" min="1" max="1440"/></label>
          <label>估算消耗（kcal，可选）<input v-model.number="after.estimatedKcal" type="number" min="0" max="20000"/></label>
          <label>备注<input v-model="after.note" maxlength="500"/></label>
        </template>
        <template v-else>
          <label>体重 kg<input v-model.number="after.weightKg" type="number" min="0.1" max="500" step="0.01"/></label>
          <label>体脂率 %（可选）<input v-model.number="after.bodyFatPct" type="number" min="0" max="100" step="0.1"/></label>
          <label>腰围 cm（可选）<input v-model.number="after.waistCm" type="number" min="0" max="300" step="0.1"/></label>
        </template>
      </template>
      <label v-else class="delete-confirm">
        <input v-model="deleteAcknowledged" type="checkbox"/>
        我确认删除所选这条记录，并理解此操作不能在此界面撤销
      </label>
      <small>确认时会重新验证记录归属及原始内容。若已被他人操作改变，则拒绝本次变更。草稿有效期15分钟。</small>
      <div class="change-row">
        <button :disabled="saving||action==='delete'&&!deleteAcknowledged" @click="confirm">
          {{ saving?'提交中…':action==='delete'?'确认删除':'确认修改' }}
        </button>
        <button class="secondary" @click="draft=null">取消</button>
      </div>
    </div>
    <router-link v-if="done" :to="done">完成，查看健康中心 →</router-link>
  </section>
</template>

<style scoped>
.wellness-change{display:grid;gap:12px;padding:14px;border:1px solid var(--el-border-color,#ddd);border-radius:12px;min-width:0;background:var(--el-bg-color,#fff)}
.wellness-change label{display:grid;gap:5px;font-size:13px;min-width:0;flex:1}
.wellness-change input:not([type=checkbox]),.wellness-change textarea,.wellness-change select{box-sizing:border-box;width:100%;min-width:0;font:inherit;font-size:16px;padding:8px;border:1px solid var(--el-border-color,#ddd);border-radius:8px;background:var(--el-bg-color,#fff);color:var(--el-text-color-primary,#222)}
.wellness-change small{font-size:12px;line-height:1.5;color:var(--el-text-color-secondary,#777)}
.wellness-change button{border:0;border-radius:8px;padding:10px 12px;background:#287fba;color:white;font-size:14px;cursor:pointer}
.wellness-change button:disabled{opacity:.55}
.wellness-change button.secondary{background:var(--el-fill-color-light,#eee);color:var(--el-text-color-primary,#222)}
.change-row{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.change-preview{display:grid;gap:9px;border:1px solid var(--el-border-color-light,#ddd);border-radius:8px;padding:12px}
.change-preview pre{font-size:12px;white-space:pre-wrap;word-break:break-all;background:var(--el-fill-color-light,#eee);padding:8px;max-height:180px;overflow:auto}
.change-error{color:var(--el-color-danger,#b44)}
.delete-confirm{display:flex!important;align-items:center;gap:8px}
</style>