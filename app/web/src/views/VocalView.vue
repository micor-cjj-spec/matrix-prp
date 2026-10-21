<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Calendar, TrendCharts, Timer, ChatLineRound, Check, Headset, Microphone } from '@element-plus/icons-vue'
import AppLayout from '@/layouts/AppLayout.vue'
import { vocalApi, type VocalExercise, type VocalTake, type PitchPoint } from '@/api/vocal'
import { useVocalRecorder } from '@/composables/useVocalRecorder'
import { displayNote, lastPitchCurve } from '@/utils/vocalPitch'

type PendingTake = {
  blob: Blob
  points: PitchPoint[]
  seconds: number
  code: string
  note: string
  peakRms: number
  analysisAvailable: boolean
}

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
const previewUrl = ref('')
const pending = ref<PendingTake | null>(null)
const microphone = useVocalRecorder()

const targetSongs = [
  { title: '可惜没如果', artist: '林俊杰', stage: '主攻候选', focus: '副歌音准、气息与情绪推进' },
  { title: '那些你很冒险的梦', artist: '林俊杰', stage: '候选曲目', focus: '高音衔接、段落层次与稳定完成' },
]
const exercise = computed(() => exercises.value.find(item => item.code === selected.value))
const curve = computed(() => lastPitchCurve(microphone.points.value))
const recordedMinutes = computed(() => Math.round(takes.value.reduce((sum, take) => sum + take.durationSeconds, 0) / 60))
const weekTakes = computed(() => takes.value.filter(take => {
  const date = new Date(take.createdAt)
  const cutoff = new Date()
  cutoff.setHours(0, 0, 0, 0)
  cutoff.setDate(cutoff.getDate() - 6)
  return date >= cutoff
}))
const weekMinutes = computed(() => Math.round(weekTakes.value.reduce((sum, take) => sum + take.durationSeconds, 0) / 60))
const reviewedTakes = computed(() => takes.value.filter(take => take.aiStatus === 'DONE').length)
const todayTakes = computed(() => {
  const today = new Date()
  return takes.value.filter(take => {
    const date = new Date(take.createdAt)
    return date.getFullYear() === today.getFullYear() &&
      date.getMonth() === today.getMonth() && date.getDate() === today.getDate()
  })
})
const inputPercent = computed(() => Math.max(0, Math.min(100, Math.round(microphone.inputRms.value * 1000))))
const inputStatus = computed(() => {
  if (!microphone.recording.value) return '等待开始录音'
  if (microphone.trackState.value === 'muted') return '系统暂时静音了麦克风'
  if (microphone.trackState.value === 'ended') return '麦克风连接已中断'
  if (!microphone.analysisAvailable.value) return '录音仍可进行，但当前浏览器无法读取音量'
  if (microphone.inputRms.value < 0.003) return '麦克风已连接，暂未检测到明显声音'
  return '正在采集声音'
})
const previewHasInput = computed(() => Boolean(pending.value && pending.value.peakRms >= 0.003))
const exerciseName = (code: string) => exercises.value.find(item => item.code === code)?.name ?? code
const formatTime = (seconds: number) => String(Math.floor(seconds / 60)).padStart(2, '0') + ':' +
  String(seconds % 60).padStart(2, '0')
const formatSize = (bytes: number) => bytes < 1024 * 1024
  ? Math.max(1, Math.round(bytes / 1024)) + ' KB'
  : (bytes / (1024 * 1024)).toFixed(1) + ' MB'
const hasTodayExercise = (code: string) => todayTakes.value.some(take => take.exerciseCode === code)

onMounted(async () => {
  try {
    ;[exercises.value, takes.value] = await Promise.all([vocalApi.exercises(), vocalApi.takes()])
  } catch {
    ElMessage.error('声乐训练数据加载失败，请确认功能迁移已安装')
  } finally {
    loading.value = false
  }
})
watch(() => microphone.seconds.value, value => {
  if (value >= 180 && microphone.recording.value) void stop()
})
onBeforeUnmount(() => {
  if (playerUrl.value) URL.revokeObjectURL(playerUrl.value)
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
})

async function referenceTone() {
  try {
    const context = new AudioContext()
    await context.resume()
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
  } catch {
    ElMessage.warning('无法播放参考音，请确认手机媒体音量和浏览器音频权限')
  }
}
async function start() {
  try {
    if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = ''
    pending.value = null
    await microphone.start()
  } catch (error) {
    const message = error instanceof Error ? error.message : '无法启动录音'
    ElMessage.error(message + '。请确认使用 HTTPS、允许麦克风权限，并检查是否有其他应用占用麦克风。')
  }
}
async function stop() {
  if (!microphone.recording.value) return
  try {
    const code = selected.value
    const description = note.value
    const blob = await microphone.stop()
    pending.value = {
      blob,
      points: [...microphone.points.value],
      seconds: Math.max(1, microphone.seconds.value),
      code,
      note: description,
      peakRms: microphone.peakRms.value,
      analysisAvailable: microphone.analysisAvailable.value,
    }
    if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = URL.createObjectURL(blob)
    ElMessage.success('录音已暂存，请先试听确认，再保存到个人记录')
  } catch (error) {
    const message = error instanceof Error ? error.message : '录音失败'
    ElMessage.error(message + '。请重新录制；若反复出现，请检查浏览器录音权限。')
  }
}
async function save() {
  if (!pending.value || saving.value) return
  saving.value = true
  try {
    const take = pending.value
    await vocalApi.upload(take.blob, take.code, take.note, take.seconds, take.points)
    pending.value = null
    if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = ''
    takes.value = await vocalApi.takes()
    ElMessage.success('录音已保存到个人训练记录')
  } catch {
    ElMessage.error('录音保存失败，原始录音仍暂存在此页面，可检查网络后重试')
  } finally {
    saving.value = false
  }
}
function discardPending() {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
  pending.value = null
}
function selectExercise(code: string) {
  selected.value = code
  document.getElementById('vocal-recorder')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}
function prepareSongPractice(song: typeof targetSongs[number]) {
  selected.value = 'phrase'
  note.value = '歌曲练习：《' + song.title + '》｜重点：' + song.focus
  ElMessage.info('已填入歌曲练习目标。录音保存后，可在训练记录中查看本次练习。')
  document.getElementById('vocal-recorder')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}
async function play(take: VocalTake) {
  loadingAudio.value = take.id
  try {
    const blob = await vocalApi.audio(take.id)
    if (playerUrl.value) URL.revokeObjectURL(playerUrl.value)
    playerUrl.value = URL.createObjectURL(blob)
    playerId.value = take.id
  } catch {
    ElMessage.error('录音读取失败')
  } finally {
    loadingAudio.value = null
  }
}
async function coach(take: VocalTake) {
  analyzing.value = take.id
  try {
    await vocalApi.coach(take.id)
    takes.value = await vocalApi.takes()
    ElMessage.success('AI 训练建议已生成')
  } catch {
    ElMessage.error('AI 暂不可用；请检查模型配置、额度或稍后重试')
  } finally {
    analyzing.value = null
  }
}
async function remove(take: VocalTake) {
  try {
    await ElMessageBox.confirm('删除后录音和相关分析无法恢复。', '删除练习记录', { type: 'warning' })
    await vocalApi.remove(take.id)
    if (playerId.value === take.id) {
      if (playerUrl.value) URL.revokeObjectURL(playerUrl.value)
      playerUrl.value = ''
      playerId.value = null
    }
    takes.value = await vocalApi.takes()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error('删除失败')
  }
}
</script>

<template>
  <AppLayout>
    <div class="vocal-page" v-loading="loading">
      <header class="vocal-hero">
        <div class="vocal-hero-copy">
          <p class="vocal-eyebrow">LEARNING · VOCAL STUDIO</p>
          <h1>声乐训练工作台</h1>
          <p>把每一次练习变成可回顾的进步：明确目标、录音验证、复盘并安排下一步。</p>
        </div>
        <div class="vocal-hero-stats">
          <div><strong>{{ takes.length }}</strong><span>次练习记录</span></div>
          <div><strong>{{ recordedMinutes }}</strong><span>累计录音分钟</span></div>
        </div>
      </header>

      <section class="vocal-metrics" aria-label="声乐训练统计">
        <article class="vocal-metric">
          <span class="metric-icon"><el-icon><Calendar /></el-icon></span>
          <div><strong>{{ todayTakes.length }}</strong><span>今日练习记录</span></div>
        </article>
        <article class="vocal-metric">
          <span class="metric-icon"><el-icon><TrendCharts /></el-icon></span>
          <div><strong>{{ weekTakes.length }}</strong><span>近 7 天练习次数</span></div>
        </article>
        <article class="vocal-metric">
          <span class="metric-icon"><el-icon><Timer /></el-icon></span>
          <div><strong>{{ weekMinutes }}</strong><span>近 7 天录音分钟</span></div>
        </article>
        <article class="vocal-metric">
          <span class="metric-icon"><el-icon><ChatLineRound /></el-icon></span>
          <div><strong>{{ reviewedTakes }}</strong><span>已有 AI 训练建议</span></div>
        </article>
      </section>

      <section class="vocal-dashboard">
        <article class="vocal-panel">
          <div class="section-heading">
            <div><p class="section-kicker">TODAY'S ROUTINE</p><h2>今日练习计划</h2></div>
            <span class="section-duration">约 15 分钟</span>
          </div>
          <p class="vocal-description">从轻柔热身开始，再进入音准与乐句练习。完成后会在下方留下记录。</p>
          <div class="vocal-plan-list">
            <button v-for="item in exercises" :key="item.code" type="button"
              class="vocal-plan-item" :class="{ 'is-complete': hasTodayExercise(item.code), 'is-selected': selected === item.code }"
              @click="selectExercise(item.code)">
              <span class="plan-check"><el-icon><Check /></el-icon></span>
              <span class="plan-copy"><strong>{{ item.name }}</strong><small>{{ item.description }}</small></span>
              <span class="plan-duration">{{ item.minutes }} 分钟</span>
            </button>
          </div>
          <p class="plan-footnote">圆形标记表示今天已有该类型的录音记录，不代表专业老师已确认完成。</p>
        </article>

        <article class="vocal-panel">
          <div class="section-heading">
            <div><p class="section-kicker">SONG GOALS</p><h2>当前目标曲目</h2></div>
            <span class="section-duration">2 首候选</span>
          </div>
          <p class="vocal-description">先从熟悉的歌曲开始，记录每次练习重点；后续再扩展完整的歌曲库与段落管理。</p>
          <div class="vocal-song-list">
            <article v-for="song in targetSongs" :key="song.title" class="vocal-song">
              <div class="song-art"><el-icon><Headset /></el-icon></div>
              <div class="song-copy">
                <strong>{{ song.title }}</strong>
                <span>{{ song.artist }} · {{ song.stage }}</span>
                <small>{{ song.focus }}</small>
              </div>
              <el-button size="small" plain @click="prepareSongPractice(song)">开始练习</el-button>
            </article>
          </div>
          <p class="plan-footnote">当前曲目来自已有音乐学习目标；此版本先关联到练习备注，持久化歌曲库将在后续阶段建设。</p>
        </article>
      </section>

      <div class="vocal-layout">
        <section id="vocal-recorder" class="vocal-panel recorder-panel">
          <div class="section-heading">
            <div><p class="section-kicker">PRACTICE SESSION</p><h2>开始一次练习</h2></div>
            <span class="recording-limit">单次最多 3 分钟</span>
          </div>
          <p class="vocal-description">首次录音时请允许麦克风权限。结束后先试听，再决定是否保存，避免把静音录音误存为有效练习。</p>

          <div class="vocal-exercises">
            <button v-for="item in exercises" :key="item.code" type="button"
              :disabled="microphone.recording.value || saving || !!pending"
              :class="{ active: selected === item.code }" @click="selected = item.code">
              <strong>{{ item.name }}</strong>
              <span>{{ item.minutes }} 分钟 · {{ item.description }}</span>
            </button>
          </div>

          <div class="vocal-reading">
            <div><span>当前音高（设备估算）</span><strong>{{ displayNote(microphone.currentHz.value) }}</strong></div>
            <div><span>频率</span><strong>{{ microphone.currentHz.value ?? '—' }} <small>Hz</small></strong></div>
            <div><span>录音时长</span><strong>{{ formatTime(microphone.seconds.value) }}</strong></div>
          </div>

          <div class="vocal-input-status" :class="{ 'is-recording': microphone.recording.value, 'is-muted': microphone.trackState.value === 'muted' || microphone.trackState.value === 'ended' }">
            <div class="input-status-copy">
              <span class="input-status-dot"></span>
              <strong>{{ inputStatus }}</strong>
              <small v-if="microphone.recording.value && microphone.analysisAvailable.value">
                输入 RMS：{{ microphone.inputRms.value.toFixed(4) }}
              </small>
            </div>
            <div class="vocal-meter" role="meter" aria-label="麦克风输入音量" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="inputPercent">
              <span :style="{ width: inputPercent + '%' }"></span>
            </div>
          </div>

          <svg class="vocal-curve" viewBox="0 0 300 100" role="img" aria-label="最近的实时音高曲线（非专业音准评分）">
            <path d="M0 25H300 M0 50H300 M0 75H300" stroke="currentColor" stroke-opacity=".10"/>
            <polyline v-if="curve" :points="curve" fill="none" stroke="currentColor" stroke-width="2.5"/>
          </svg>

          <p class="vocal-description">
            {{ exercise?.description || '请选择一个练习' }}
            <span v-if="exercise?.targetHz"> · 参考音 {{ exercise.targetHz }} Hz</span>
          </p>
          <el-input v-model="note" :disabled="microphone.recording.value || saving || !!pending"
            type="textarea" :rows="2" maxlength="500" show-word-limit
            placeholder="本次练习重点，例如：副歌换气、某句高音、老师布置的作业"/>
          <div class="vocal-actions">
            <el-button :disabled="microphone.recording.value || saving || !!pending" @click="referenceTone">试听参考音</el-button>
            <el-button v-if="!microphone.recording.value" type="primary"
              :disabled="saving || !microphone.supported.value || !!pending" @click="start">开始录音</el-button>
            <el-button v-else type="danger" @click="stop">结束录音并试听</el-button>
          </div>

          <div v-if="pending && previewUrl" class="vocal-preview">
            <div class="preview-heading">
              <div><strong>录音预览</strong><span>{{ formatTime(pending.seconds) }} · {{ formatSize(pending.blob.size) }}</span></div>
              <el-tag v-if="previewHasInput" type="success">检测到输入</el-tag>
              <el-tag v-else type="warning">输入音量偏低</el-tag>
            </div>
            <audio :src="previewUrl" controls preload="metadata" class="vocal-audio"/>
            <p v-if="!previewHasInput && pending.analysisAvailable" class="vocal-warning">
              实时音量检测未发现明显声音。麦克风图标只表示权限/采集会话已启动，请先播放上方录音确认是否有声音；若是静音，请重新录制并检查 iPhone 的麦克风权限和输入环境。
            </p>
            <p v-else-if="!pending.analysisAvailable" class="vocal-description">
              当前浏览器未能提供实时音量分析，请以本机试听结果为准。音高曲线可能为空，但录音仍可保存。
            </p>
            <p v-else-if="pending.points.length === 0" class="vocal-description">
              已采集到声音，但没有检测到稳定的单音。普通说话、伴奏或滑音不一定能生成音高点；可试听确认后保存。
            </p>
            <div class="vocal-actions">
              <el-button type="primary" :loading="saving" @click="save">确认并保存</el-button>
              <el-button :disabled="saving" @click="discardPending">丢弃并重新录制</el-button>
            </div>
          </div>

          <p class="vocal-disclaimer">
            录音最多 3 分钟；原始录音只会在你点击“确认并保存”后上传到个人私有空间。音量和音高均为设备端粗略测量，不是专业声乐评估或医学检测。
          </p>
        </section>

        <section class="vocal-panel history-panel">
          <div class="section-heading">
            <div><p class="section-kicker">PRACTICE HISTORY</p><h2>练习与复盘</h2></div>
            <span class="section-duration">最近 {{ takes.length }} 条</span>
          </div>
          <div v-if="!takes.length" class="vocal-empty">
            <el-icon><Microphone /></el-icon>
            <strong>还没有练习记录</strong>
            <span>完成第一次录音并确认保存后，这里会显示你的练习历史。</span>
          </div>
          <div v-for="take in takes" :key="take.id" class="vocal-take">
            <div class="vocal-take-title">
              <div><strong>{{ exerciseName(take.exerciseCode) }}</strong>
                <small>{{ new Date(take.createdAt).toLocaleString() }} · {{ formatTime(take.durationSeconds) }}</small>
              </div>
              <el-button text type="danger" size="small" @click="remove(take)">删除</el-button>
            </div>
            <p v-if="take.note" class="vocal-description">{{ take.note }}</p>
            <div class="vocal-metrics">
              <span>音高采样 <b>{{ take.analysis.voicedSamples }}</b></span>
              <span>中位频率 <b>{{ take.analysis.medianHz ?? '—' }} Hz</b></span>
              <span v-if="take.analysis.targetHitPercent !== null">参考音命中 <b>{{ take.analysis.targetHitPercent }}%</b></span>
            </div>
            <p class="vocal-description">{{ take.analysis.guidance }}</p>
            <div class="vocal-actions">
              <el-button size="small" :loading="loadingAudio === take.id" @click="play(take)">播放录音</el-button>
              <el-button size="small" :loading="analyzing === take.id" :disabled="analyzing !== null"
                @click="coach(take)">{{ take.aiStatus === 'DONE' ? '查看 AI 建议' : '生成 AI 训练建议' }}</el-button>
            </div>
            <audio v-if="playerId === take.id && playerUrl" :src="playerUrl" controls preload="none" class="vocal-audio"/>
            <p v-if="take.aiFeedback" class="vocal-ai"><strong>AI 训练建议：</strong>{{ take.aiFeedback }}</p>
          </div>
          <p class="vocal-disclaimer">当前 AI 读取练习名称、文字备注和设备估算指标，不会听取原始录音。未指定参考音的练习不会生成音准分数。</p>
        </section>
      </div>
    </div>
  </AppLayout>
</template>

<style scoped>
.vocal-page{max-width:1240px;margin:0 auto;padding:24px 16px 60px}
.vocal-hero{display:flex;justify-content:space-between;align-items:center;gap:22px;margin-bottom:22px}
.vocal-hero h1{font-size:clamp(25px,4vw,34px);letter-spacing:-.03em;margin:7px 0}
.vocal-hero p{color:var(--el-text-color-secondary);margin:7px 0;font-size:14px;line-height:1.65}
.vocal-eyebrow,.section-kicker{font-size:10px!important;letter-spacing:1.7px;font-weight:700;color:var(--el-color-primary)!important}
.vocal-hero-stats{display:flex;gap:10px;flex-shrink:0}
.vocal-hero-stats div{min-width:105px;padding:14px 16px;background:var(--el-fill-color-light);border:1px solid var(--el-border-color-lighter);border-radius:14px}
.vocal-hero-stats strong,.vocal-hero-stats span{display:block}
.vocal-hero-stats strong{font-size:25px;font-variant-numeric:tabular-nums}
.vocal-hero-stats span{font-size:12px;color:var(--el-text-color-secondary);margin-top:3px}
.vocal-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:16px}
.vocal-metric{display:flex;align-items:center;gap:12px;padding:15px;border:1px solid var(--el-border-color-lighter);border-radius:15px;background:var(--el-bg-color)}
.metric-icon{display:grid;place-items:center;width:40px;height:40px;border-radius:12px;background:var(--el-fill-color-light);color:var(--el-color-primary);font-size:19px;flex-shrink:0}
.vocal-metric strong,.vocal-metric span:not(.metric-icon){display:block}
.vocal-metric strong{font-size:22px;line-height:1.2;font-variant-numeric:tabular-nums}
.vocal-metric div span{font-size:12px;color:var(--el-text-color-secondary);margin-top:4px}
.vocal-dashboard{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px;align-items:stretch}
.vocal-panel{border:1px solid var(--el-border-color-lighter);border-radius:18px;padding:20px;min-width:0;background:var(--el-bg-color)}
.section-heading{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:8px}
.section-heading h2{font-size:18px;margin:3px 0 0;letter-spacing:-.02em}
.section-kicker{margin:0!important}
.section-duration,.recording-limit{font-size:11px;color:var(--el-text-color-secondary);padding:6px 9px;border-radius:99px;background:var(--el-fill-color-light);white-space:nowrap}
.vocal-description,.vocal-disclaimer{color:var(--el-text-color-secondary);font-size:13px;line-height:1.65;overflow-wrap:anywhere}
.vocal-disclaimer{font-size:11px;margin:14px 0 0}
.vocal-plan-list{display:grid;gap:7px;margin-top:14px}
.vocal-plan-item{display:flex;align-items:center;gap:10px;width:100%;text-align:left;border:1px solid var(--el-border-color-lighter);border-radius:11px;padding:10px;background:var(--el-bg-color);color:var(--el-text-color-primary);cursor:pointer}
.vocal-plan-item:hover,.vocal-plan-item.is-selected{border-color:var(--el-color-primary)}
.vocal-plan-item.is-selected{background:var(--el-color-primary-light-9)}
.plan-check{display:grid;place-items:center;width:25px;height:25px;border:1px solid var(--el-border-color);border-radius:50%;color:transparent;flex-shrink:0}
.vocal-plan-item.is-complete .plan-check{background:var(--el-color-success-light-8);border-color:var(--el-color-success);color:var(--el-color-success)}
.plan-copy{min-width:0;flex:1}
.plan-copy strong,.plan-copy small{display:block}
.plan-copy strong{font-size:13px}
.plan-copy small{font-size:11px;line-height:1.4;color:var(--el-text-color-secondary);margin-top:3px}
.plan-duration{font-size:11px;color:var(--el-text-color-secondary);white-space:nowrap}
.plan-footnote{font-size:11px;color:var(--el-text-color-secondary);line-height:1.55;margin:12px 0 0}
.vocal-song-list{display:grid;gap:10px;margin-top:14px}
.vocal-song{display:flex;align-items:center;gap:11px;padding:12px;border:1px solid var(--el-border-color-lighter);border-radius:13px;min-width:0}
.song-art{display:grid;place-items:center;width:42px;height:42px;flex-shrink:0;border-radius:12px;background:var(--el-fill-color-light);font-size:20px;color:var(--el-color-primary)}
.song-copy{min-width:0;flex:1}
.song-copy strong,.song-copy span,.song-copy small{display:block}
.song-copy strong{font-size:14px}
.song-copy span{font-size:11px;color:var(--el-text-color-secondary);margin-top:3px}
.song-copy small{font-size:11px;color:var(--el-text-color-secondary);line-height:1.5;margin-top:4px}
.vocal-layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;align-items:start}
.vocal-exercises{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin:14px 0}
.vocal-exercises button{text-align:left;border:1px solid var(--el-border-color);border-radius:12px;padding:12px;background:var(--el-bg-color);color:var(--el-text-color-primary);cursor:pointer;min-width:0}
.vocal-exercises button.active{border-color:var(--el-color-primary);background:var(--el-color-primary-light-9)}
.vocal-exercises button:disabled{opacity:.65;cursor:not-allowed}
.vocal-exercises button strong{font-size:13px}
.vocal-exercises button span{display:block;font-size:11px;line-height:1.5;color:var(--el-text-color-secondary);margin-top:5px}
.vocal-reading{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:13px 0}
.vocal-reading div{background:var(--el-fill-color-light);padding:10px;border-radius:10px;min-width:0}
.vocal-reading span,.vocal-reading strong{display:block}
.vocal-reading span{font-size:10px;line-height:1.4;color:var(--el-text-color-secondary)}
.vocal-reading strong{font-size:clamp(17px,2vw,21px);margin-top:7px;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.vocal-reading small{font-size:11px;font-weight:normal}
.vocal-input-status{padding:12px;border:1px solid var(--el-border-color-lighter);border-radius:12px;background:var(--el-fill-color-lighter)}
.input-status-copy{display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.input-status-copy strong{font-size:12px}
.input-status-copy small{font-size:10px;color:var(--el-text-color-secondary);margin-left:auto}
.input-status-dot{width:8px;height:8px;border-radius:50%;background:var(--el-text-color-placeholder);flex-shrink:0}
.vocal-input-status.is-recording .input-status-dot{background:var(--el-color-success);box-shadow:0 0 0 4px var(--el-color-success-light-8)}
.vocal-input-status.is-muted .input-status-dot{background:var(--el-color-warning)}
.vocal-meter{height:7px;border-radius:99px;background:var(--el-border-color-lighter);overflow:hidden;margin-top:10px}
.vocal-meter span{display:block;height:100%;min-width:0;border-radius:99px;background:var(--el-color-success);transition:width .1s linear}
.vocal-curve{width:100%;height:105px;margin:12px 0;background:var(--el-fill-color-light);border-radius:12px;color:var(--el-color-primary)}
.vocal-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.vocal-actions .el-button+.el-button{margin-left:0}
.vocal-preview{border:1px solid var(--el-border-color);border-radius:14px;padding:13px;margin-top:16px;background:var(--el-fill-color-lighter)}
.preview-heading{display:flex;align-items:center;justify-content:space-between;gap:10px}
.preview-heading strong,.preview-heading span{display:block}
.preview-heading strong{font-size:14px}
.preview-heading span{font-size:11px;color:var(--el-text-color-secondary);margin-top:4px}
.vocal-warning{font-size:12px;line-height:1.65;color:var(--el-color-warning-dark-2);background:var(--el-color-warning-light-9);padding:10px;border-radius:9px}
.vocal-take{border-top:1px solid var(--el-border-color-lighter);padding:15px 0}
.vocal-take-title{display:flex;align-items:start;justify-content:space-between;gap:8px}
.vocal-take-title strong{font-size:14px}
.vocal-take-title small{display:block;margin-top:5px;color:var(--el-text-color-secondary);font-size:11px}
.vocal-metrics{display:flex;gap:7px;flex-wrap:wrap;margin:10px 0}
.vocal-metrics span{font-size:11px;background:var(--el-fill-color-light);padding:7px;border-radius:7px}
.vocal-ai{background:var(--el-color-primary-light-9);padding:11px;border-radius:10px;white-space:pre-wrap;font-size:12px;line-height:1.7;overflow-wrap:anywhere}
.vocal-audio{width:100%;margin-top:12px}
.vocal-empty{display:flex;flex-direction:column;align-items:center;gap:8px;padding:42px 16px;color:var(--el-text-color-secondary);text-align:center}
.vocal-empty .el-icon{font-size:28px}
.vocal-empty strong{font-size:14px;color:var(--el-text-color-primary)}
.vocal-empty span{font-size:12px;line-height:1.6}
@media(max-width:980px){.vocal-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.vocal-dashboard,.vocal-layout{grid-template-columns:1fr}}
@media(max-width:600px){.vocal-page{padding:18px 12px 42px}.vocal-hero{align-items:flex-start;flex-direction:column}.vocal-hero-stats{width:100%}.vocal-hero-stats div{flex:1;min-width:0}.vocal-panel{padding:15px}.vocal-exercises{grid-template-columns:1fr 1fr}.vocal-song{align-items:flex-start;flex-wrap:wrap}.vocal-song .el-button{margin-left:53px}.input-status-copy small{width:100%;margin-left:15px}.vocal-reading{gap:6px}.vocal-reading div{padding:8px}}
@media(max-width:360px){.vocal-exercises{grid-template-columns:1fr}.section-heading{align-items:flex-start;flex-direction:column}}
</style>
