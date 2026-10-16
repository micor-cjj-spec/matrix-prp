<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '@/layouts/AppLayout.vue'
import { vocalApi, type VocalExercise, type VocalTake, type PitchPoint } from '@/api/vocal'
import { useVocalRecorder } from '@/composables/useVocalRecorder'
import { displayNote, lastPitchCurve } from '@/utils/vocalPitch'

const exercises = ref<VocalExercise[]>([])
const takes = ref<VocalTake[]>([])
const loading = ref(true)
const selected = ref('hum')
const note = ref('')
const saving = ref(false)
const analyzing = ref<number | null>(null)
const loadingAudio = ref<number | null>(null)
const playerUrl = ref('')
const playerId = ref<number | null>(null)
const pending = ref<{ blob: Blob; points: PitchPoint[]; seconds: number; code: string; note: string } | null>(null)
const microphone = useVocalRecorder()
const exercise = computed(() => exercises.value.find(e => e.code === selected.value))
const curve = computed(() => lastPitchCurve(microphone.points.value))
const recordedMinutes = computed(() => Math.round(takes.value.reduce((acc, t) => acc + t.durationSeconds, 0) / 60))
const exerciseName = (code: string) => exercises.value.find(e => e.code === code)?.name ?? code
const formatTime = (seconds: number) => String(Math.floor(seconds / 60)).padStart(2,'0') + ':' +
  String(seconds % 60).padStart(2,'0')

onMounted(async () => {
  try { [exercises.value, takes.value] = await Promise.all([vocalApi.exercises(), vocalApi.takes()]) }
  catch { ElMessage.error('声乐训练数据加载失败，请确认功能迁移已安装') }
  finally { loading.value = false }
})
watch(() => microphone.seconds.value, value => {
  if (value >= 180 && microphone.recording.value) void stop()
})
onBeforeUnmount(() => { if (playerUrl.value) URL.revokeObjectURL(playerUrl.value) })

async function referenceTone() {
  try {
    const context = new AudioContext()
    const tone = context.createOscillator()
    const gain = context.createGain()
    tone.frequency.value = exercise.value?.targetHz || 440
    tone.type = 'sine'
    gain.gain.setValueAtTime(0.001, context.currentTime)
    gain.gain.linearRampToValueAtTime(0.035, context.currentTime + 0.04)
    gain.gain.linearRampToValueAtTime(0.001, context.currentTime + 0.8)
    tone.connect(gain).connect(context.destination)
    tone.start()
    tone.stop(context.currentTime + 0.82)
    tone.onended = () => { void context.close() }
  } catch { ElMessage.warning('无法播放参考音') }
}
async function start() {
  try { await microphone.start() }
  catch { ElMessage.error('无法访问麦克风，请检查 HTTPS 与浏览器权限') }
}
async function stop() {
  if (!microphone.recording.value) return
  try {
    const code = selected.value, description = note.value
    const blob = await microphone.stop()
    pending.value = {
      blob, points: [...microphone.points.value],
      seconds: Math.max(1, microphone.seconds.value),
      code, note: description,
    }
    await save()
  } catch { ElMessage.error('录音失败，请重试') }
}
async function save() {
  if (!pending.value || saving.value) return
  saving.value = true
  try {
    const p = pending.value
    await vocalApi.upload(p.blob, p.code, p.note, p.seconds, p.points)
    pending.value = null
    takes.value = await vocalApi.takes()
    ElMessage.success('录音及音高观测数据已保存')
  } catch { ElMessage.error('录音保存失败，原始录音暂留在此页面，可点击重试') }
  finally { saving.value = false }
}
async function play(take: VocalTake) {
  loadingAudio.value = take.id
  try {
    const blob = await vocalApi.audio(take.id)
    if (playerUrl.value) URL.revokeObjectURL(playerUrl.value)
    playerUrl.value = URL.createObjectURL(blob)
    playerId.value = take.id
  } catch { ElMessage.error('录音读取失败') }
  finally { loadingAudio.value = null }
}
async function coach(take: VocalTake) {
  analyzing.value = take.id
  try {
    await vocalApi.coach(take.id)
    takes.value = await vocalApi.takes()
    ElMessage.success('AI 建议已生成')
  } catch { ElMessage.error('AI 暂不可用；请检查模型配置、额度或稍后重试') }
  finally { analyzing.value = null }
}
async function remove(take: VocalTake) {
  try {
    await ElMessageBox.confirm('删除后录音和相关分析无法恢复。', '删除练习记录', { type: 'warning' })
    await vocalApi.remove(take.id)
    if (playerId.value === take.id) {
      URL.revokeObjectURL(playerUrl.value); playerUrl.value = ''; playerId.value = null
    }
    takes.value = await vocalApi.takes()
  } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error('删除失败') }
}
</script>

<template>
  <AppLayout>
    <div class="vocal-page" v-loading="loading">
      <header class="vocal-hero">
        <div>
          <p class="vocal-eyebrow">LEARNING · VOCAL STUDIO</p>
          <h1>声乐训练中心</h1>
          <p>从轻柔发声开始，录下每一次进步。练习中如有疼痛或明显嘶哑请停止。</p>
        </div>
        <div class="vocal-summary">
          <span><strong>{{ takes.length }}</strong>次练习</span>
          <span><strong>{{ recordedMinutes }}</strong>分钟录音</span>
        </div>
      </header>

      <div class="vocal-layout">
        <section class="vocal-panel">
          <h2>今日练习</h2>
          <p class="vocal-description">选择一个练习；首次录音时浏览器会请求麦克风权限。</p>
          <div class="vocal-exercises">
            <button v-for="item in exercises" :key="item.code" type="button"
              :disabled="microphone.recording.value || saving" :class="{ active: selected === item.code }"
              @click="selected = item.code">
              <strong>{{ item.name }}</strong>
              <span>{{ item.minutes }} 分钟 · {{ item.description }}</span>
            </button>
          </div>

          <div class="vocal-recorder">
            <div class="vocal-reading">
              <div><span>当前音高（设备估算）</span><strong>{{ displayNote(microphone.currentHz.value) }}</strong></div>
              <div><span>频率</span><strong>{{ microphone.currentHz.value ?? '—' }} <small>Hz</small></strong></div>
              <div><span>录音时长</span><strong>{{ formatTime(microphone.seconds.value) }}</strong></div>
            </div>
            <svg class="vocal-curve" viewBox="0 0 300 100" role="img" aria-label="最近的实时音高曲线（非音准评分）">
              <path d="M0 25H300 M0 50H300 M0 75H300" stroke="currentColor" stroke-opacity=".10"/>
              <polyline v-if="curve" :points="curve" fill="none" stroke="#16a085" stroke-width="2.5"/>
            </svg>
            <p class="vocal-description">
              {{ exercise?.description || '请选择一个练习' }}
              <span v-if="exercise?.targetHz"> · 参考音 {{ exercise.targetHz }} Hz</span>
            </p>
            <el-input v-model="note" :disabled="microphone.recording.value || saving" type="textarea"
              :rows="2" maxlength="500" show-word-limit placeholder="可选：这次想重点解决什么问题？"/>
            <div class="vocal-actions">
              <el-button :disabled="microphone.recording.value || saving" @click="referenceTone">试听参考音</el-button>
              <el-button v-if="!microphone.recording.value" type="primary" :disabled="saving || !microphone.supported.value || !!pending" @click="start">开始录音</el-button>
              <el-button v-else type="danger" @click="stop">结束并保存</el-button>
              <el-button v-if="pending" type="warning" :loading="saving" @click="save">重试保存</el-button>
            </div>
            <p class="vocal-disclaimer">最多录制 3 分钟；声音仅在你保存后上传到个人私有空间。音高曲线为浏览器粗略估计，不是医学检测。</p>
          </div>
        </section>

        <section class="vocal-panel">
          <h2>训练记录</h2>
          <div v-if="!takes.length" class="vocal-empty">还没有记录。完成第一次练声后，录音和客观指标会出现在这里。</div>
          <div v-for="take in takes" :key="take.id" class="vocal-take">
            <div class="vocal-take-title">
              <div><strong>{{ exerciseName(take.exerciseCode) }}</strong>
                <small>{{ new Date(take.createdAt).toLocaleString() }} · {{ formatTime(take.durationSeconds) }}</small></div>
              <el-button text type="danger" size="small" @click="remove(take)">删除</el-button>
            </div>
            <p v-if="take.note" class="vocal-description">{{ take.note }}</p>
            <div class="vocal-metrics">
              <span>有效音高采样 <b>{{ take.analysis.voicedSamples }}</b></span>
              <span>中位频率 <b>{{ take.analysis.medianHz ?? '—' }} Hz</b></span>
              <span v-if="take.analysis.targetHitPercent !== null">参考音命中 <b>{{ take.analysis.targetHitPercent }}%</b></span>
            </div>
            <p class="vocal-description">{{ take.analysis.guidance }}</p>
            <div class="vocal-actions">
              <el-button size="small" :loading="loadingAudio === take.id" @click="play(take)">播放录音</el-button>
              <el-button size="small" :loading="analyzing === take.id" :disabled="analyzing !== null" @click="coach(take)">
                {{ take.aiStatus === 'DONE' ? '查看 AI 建议' : 'AI 教练分析' }}
              </el-button>
            </div>
            <audio v-if="playerId === take.id && playerUrl" :src="playerUrl" controls preload="none" class="vocal-audio"/>
            <p v-if="take.aiFeedback" class="vocal-ai"><strong>AI 教练：</strong>{{ take.aiFeedback }}</p>
          </div>
          <p class="vocal-disclaimer">AI 仅接收练习名称、文字备注和设备估算指标，不上传原始录音给所选模型。未指定目标旋律的练习不计算音准分数。</p>
        </section>
      </div>
    </div>
  </AppLayout>
</template>

<style scoped>
.vocal-page{max-width:1180px;margin:0 auto;padding:24px 16px 60px}
.vocal-hero{display:flex;justify-content:space-between;align-items:center;gap:18px;margin-bottom:22px}
.vocal-hero h1{font-size:clamp(24px,4vw,32px);margin:6px 0}
.vocal-hero p{color:var(--el-text-color-secondary);margin:6px 0;font-size:14px}
.vocal-eyebrow{font-size:11px!important;letter-spacing:1.6px}
.vocal-summary{display:flex;gap:12px;flex-shrink:0}
.vocal-summary span{padding:12px;background:var(--el-fill-color-light);border-radius:12px;font-size:13px}
.vocal-summary strong{font-size:22px;display:block}
.vocal-layout{display:grid;grid-template-columns:1fr 1fr;gap:18px;align-items:start}
.vocal-panel{border:1px solid var(--el-border-color-lighter);border-radius:18px;padding:20px;min-width:0}
.vocal-panel h2{font-size:18px;margin:0 0 9px}
.vocal-description,.vocal-disclaimer{color:var(--el-text-color-secondary);font-size:13px;line-height:1.65;overflow-wrap:anywhere}
.vocal-disclaimer{font-size:12px;margin:12px 0 0}
.vocal-exercises{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.vocal-exercises button{text-align:left;border:1px solid var(--el-border-color);border-radius:12px;padding:12px;background:var(--el-bg-color);color:var(--el-text-color-primary);cursor:pointer}
.vocal-exercises button.active{border-color:var(--el-color-primary);background:var(--el-color-primary-light-9)}
.vocal-exercises button span{display:block;font-size:12px;line-height:1.5;color:var(--el-text-color-secondary);margin-top:5px}
.vocal-recorder{margin-top:18px}
.vocal-reading{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.vocal-reading div{background:var(--el-fill-color-light);padding:10px;border-radius:10px}
.vocal-reading span,.vocal-reading strong{display:block}
.vocal-reading span{font-size:11px;color:var(--el-text-color-secondary)}
.vocal-reading strong{font-size:21px;margin-top:7px;font-variant-numeric:tabular-nums}
.vocal-reading small{font-size:11px;font-weight:normal}
.vocal-curve{width:100%;height:110px;margin:12px 0;background:var(--el-fill-color-light);border-radius:12px}
.vocal-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.vocal-actions .el-button+.el-button{margin-left:0}
.vocal-take{border-top:1px solid var(--el-border-color-lighter);padding:16px 0}
.vocal-take-title{display:flex;align-items:start;justify-content:space-between}
.vocal-take-title small{display:block;margin-top:5px;color:var(--el-text-color-secondary)}
.vocal-metrics{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}
.vocal-metrics span{font-size:12px;background:var(--el-fill-color-light);padding:7px;border-radius:7px}
.vocal-ai{background:var(--el-color-primary-light-9);padding:10px;border-radius:10px;white-space:pre-wrap;font-size:13px;line-height:1.7}
.vocal-audio{width:100%;margin-top:12px}
.vocal-empty{padding:35px 12px;color:var(--el-text-color-secondary);text-align:center}
@media(max-width:820px){.vocal-layout{grid-template-columns:1fr}.vocal-hero{align-items:flex-start;flex-direction:column}.vocal-panel{padding:15px}.vocal-exercises{grid-template-columns:1fr 1fr}}
@media(max-width:370px){.vocal-exercises{grid-template-columns:1fr}}
</style>
