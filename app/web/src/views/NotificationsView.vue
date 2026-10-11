<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '@/layouts/AppLayout.vue'
import { notificationCategoryLabel, notificationPermissionLabel } from '@/utils/labels'
import { decodeVapidPublicKey, describePushFailure, isInstalledPwa, isIosDevice, pushStageLabels, samePublicKey, type PushStage } from '@/utils/pushDiagnostics'
import {
  getReminders, createReminder, updateReminder, changeReminderStatus, removeReminder, sendNow,
  getInbox, markRead, getDevices, getVapidKey, registerSubscription, removeDevice, testPush,
  type Frequency, type Reminder, type ReminderPayload, type InboxItem, type Device
} from '@/api/notifications'

const tab = ref('rules')
const title = ref('')
const body = ref('')
const category = ref('CUSTOM')
const scheduleType = ref<Frequency>('WEEKDAYS')
const localTime = ref('20:00')
const onceLocal = ref('')
const weekdays = ref<number[]>([1, 3, 5])
const monthDay = ref(1)
const editId = ref<number | null>(null)
const saving = ref(false)
const rules = ref<Reminder[]>([])
const inbox = ref<InboxItem[]>([])
const devices = ref<Device[]>([])
const permission = ref(typeof Notification === 'undefined' ? 'unsupported' : Notification.permission)
const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Shanghai'
const repeatLabels: Record<Frequency, string> = { ONCE: '指定时间', DAILY: '每天', WEEKDAYS: '工作日', WEEKLY: '每周', MONTHLY: '每月' }
const currentPreview = computed(() => title.value.trim() || '我的新提醒')
const supportsPush = typeof window !== 'undefined' && window.isSecureContext && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
const iosDevice = isIosDevice()
const standalonePwa = isInstalledPwa()
const subscribing = ref(false)
const pushStatus = ref('')
const pushNextStep = ref('')
async function refresh() {
  try {
    const [r, m, d] = await Promise.all([getReminders(), getInbox(), getDevices()])
    rules.value = r; inbox.value = m; devices.value = d
  } catch { ElMessage.error('加载消息中心失败，请检查数据库迁移和服务状态') }
}
function payload(): ReminderPayload {
  let onceAt: string | null = null
  if (scheduleType.value === 'ONCE') {
    const date = new Date(onceLocal.value)
    if (!onceLocal.value || Number.isNaN(date.getTime())) throw new Error('请选择有效的提醒日期和时间')
    onceAt = date.toISOString()
  }
  return {
    title: title.value.trim(), body: body.value.trim(), category: category.value,
    scheduleType: scheduleType.value, timezone,
    localTime: scheduleType.value === 'ONCE' ? null : localTime.value,
    weekdays: scheduleType.value === 'WEEKLY' ? weekdays.value.join(',') : '',
    monthDay: scheduleType.value === 'MONTHLY' ? monthDay.value : null, onceAt,
  }
}
async function save(immediate = false) {
  if (!title.value.trim() || !body.value.trim()) { ElMessage.warning('标题和正文不能为空'); return }
  saving.value = true
  try {
    const p: ReminderPayload = immediate ? {
      title: title.value.trim(), body: body.value.trim(), category: category.value,
      scheduleType: 'ONCE', timezone, localTime: null, weekdays: '', monthDay: null, onceAt: null
    } : payload()
    if (immediate) await sendNow(p)
    else if (editId.value !== null) await updateReminder(editId.value, p)
    else await createReminder(p)
    ElMessage.success(immediate ? '已创建消息，正在尝试向已订阅设备发送' : '提醒规则已保存')
    reset()
    await refresh()
  } catch (err) {
    ElMessage.error(err instanceof Error && err.message.startsWith('请选择') ? err.message : '保存失败，请检查提醒规则')
  } finally { saving.value = false }
}
function reset() {
  editId.value = null
  title.value = ''; body.value = ''; category.value = 'CUSTOM'
  scheduleType.value = 'WEEKDAYS'; localTime.value = '20:00'; onceLocal.value = ''
  weekdays.value = [1,3,5]; monthDay.value = 1
}
function edit(item: Reminder) {
  editId.value = item.id; title.value = item.title; body.value = item.body
  category.value = item.category
  scheduleType.value = item.scheduleType
  localTime.value = item.localTime || '20:00'
  weekdays.value = item.weekdays ? item.weekdays.split(',').map(Number) : []
  monthDay.value = item.monthDay || 1
  if (item.scheduleType === 'ONCE' && item.nextFireAt) onceLocal.value = item.nextFireAt.replace(' ', 'T').slice(0,16)
  tab.value = 'rules'; window.scrollTo({ top: 0, behavior: 'smooth' })
}
async function toggle(item: Reminder) {
  try { await changeReminderStatus(item.id, !item.enabled); await refresh() }
  catch { ElMessage.error('操作失败，单次提醒过期后不可恢复，请重新创建') }
}
async function remove(item: Reminder) {
  try {
    await ElMessageBox.confirm('删除提醒规则？历史消息会保留。', '确认删除')
    await removeReminder(item.id); await refresh()
  } catch { /* canceled */ }
}
async function enablePush() {
  if (subscribing.value) return
  pushStatus.value = ''
  pushNextStep.value = ''
  // iOS Web Push requires the installed home-screen web app, not a Safari tab.
  if (iosDevice && !standalonePwa) {
    pushStatus.value = '当前未在 iPhone 主屏幕应用中运行'
    pushNextStep.value = '请用 Safari 将网站添加到主屏幕，随后从桌面图标启动 Matrix PRP。'
    ElMessage.warning(pushStatus.value)
    return
  }
  if (!supportsPush) {
    const failure = describePushFailure('environment', null)
    pushStatus.value = failure.message
    pushNextStep.value = failure.nextStep
    ElMessage.warning(failure.message)
    return
  }
  subscribing.value = true
  let stage: PushStage = 'permission'
  try {
    pushStatus.value = '正在' + pushStageLabels[stage] + '…'
    // Request permission before network calls to retain the user's click gesture.
    const granted = Notification.permission === 'granted' ? 'granted' : await Notification.requestPermission()
    permission.value = granted
    if (granted !== 'granted') throw new Error('Notification permission is ' + granted)

    stage = 'vapid'
    pushStatus.value = '正在' + pushStageLabels[stage] + '…'
    const publicKey = await getVapidKey()
    if (!publicKey) throw new Error('Server VAPID public key is empty')
    const applicationServerKey = decodeVapidPublicKey(publicKey)

    stage = 'serviceWorker'
    pushStatus.value = '正在' + pushStageLabels[stage] + '…'
    // Use this app's registration, not navigator.serviceWorker.ready which can resolve
    // to a legacy root-scope worker still controlling the page after a /prp/ migration.
    const registration = await navigator.serviceWorker.register(`${import.meta.env.BASE_URL}sw.js`, { scope: import.meta.env.BASE_URL })
    await navigator.serviceWorker.ready

    stage = 'browserSubscription'
    pushStatus.value = '正在' + pushStageLabels[stage] + '…'
    let subscription = await registration.pushManager.getSubscription()
    if (subscription && !samePublicKey(subscription.options.applicationServerKey, applicationServerKey)) {
      // A rotated VAPID key cannot work with a subscription bound to the old key.
      const removed = await subscription.unsubscribe()
      if (!removed) throw new Error('Previous VAPID subscription could not be removed')
      subscription = null
    }
    if (!subscription) {
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: applicationServerKey as BufferSource,
      })
    }
    const json = subscription.toJSON()
    if (!json.keys?.p256dh || !json.keys.auth) throw new Error('Incomplete browser subscription keys')

    stage = 'serverRegistration'
    pushStatus.value = '正在' + pushStageLabels[stage] + '…'
    await registerSubscription({
      endpoint: subscription.endpoint,
      p256dh: json.keys.p256dh,
      auth: json.keys.auth,
      deviceName: iosDevice ? 'iPhone 主屏幕应用' : '网页浏览器',
    })
    pushStatus.value = '当前设备已成功订阅推送'
    pushNextStep.value = '可以点击“发送测试通知”验证实际投递。'
    ElMessage.success('当前设备已订阅推送')
    await refresh()
  } catch (error) {
    // Log only the stage, exception type and HTTP status; never log subscription keys or JWT.
    const status = (error as { response?: { status?: unknown } } | null)?.response?.status
    console.error('[Matrix PRP Push]', {
      stage,
      errorName: error instanceof Error ? error.name : 'UnknownError',
      httpStatus: typeof status === 'number' ? status : undefined,
    })
    const failure = describePushFailure(stage, error)
    pushStatus.value = failure.message
    pushNextStep.value = failure.nextStep
    ElMessage.error({ message: failure.message, duration: 6000, showClose: true })
  } finally {
    subscribing.value = false
  }
}
async function sendTest() {
  try { await testPush(); ElMessage.success('测试消息已写入收件箱，正在投递已订阅设备'); await refresh() }
  catch { ElMessage.error('测试发送失败') }
}
async function acknowledge(item: InboxItem) {
  if (item.readAt) return
  try { await markRead(item.id); await refresh() } catch { ElMessage.error('标记已读失败') }
}
async function revokeDevice(device: Device) {
  try { await removeDevice(device.id); await refresh(); ElMessage.success('设备已从服务器移除') }
  catch { ElMessage.error('删除设备失败') }
}
onMounted(refresh)
</script>

<template>
  <AppLayout>
    <header class="page-header">
      <div>
        <p class="eyebrow">消息管理</p>
        <h1>消息与提醒中心</h1>
        <p>创建自己的提醒规则，接收 iPhone 和电脑上的系统通知。</p>
      </div>
    </header>
    <el-tabs v-model="tab">
      <el-tab-pane label="我的提醒" name="rules">
        <div class="notification-grid">
          <el-card shadow="never">
            <template #header><strong>{{ editId === null ? '新建自定义提醒' : '编辑提醒' }}</strong></template>
            <el-form label-position="top">
              <el-form-item label="通知标题">
                <el-input v-model="title" maxlength="120" show-word-limit placeholder="例如：软考学习提醒" />
              </el-form-item>
              <el-form-item label="通知内容">
                <el-input v-model="body" type="textarea" :rows="3" maxlength="500" show-word-limit placeholder="输入提醒内容" />
              </el-form-item>
              <el-form-item label="分类">
                <el-select v-model="category">
                  <el-option label="自定义" value="CUSTOM" /><el-option label="学习" value="STUDY" />
                  <el-option label="工作" value="WORK" /><el-option label="生活" value="LIFE" />
                  <el-option label="财务" value="FINANCE" />
                </el-select>
              </el-form-item>
              <el-form-item label="重复周期">
                <el-select v-model="scheduleType">
                  <el-option v-for="(label,key) in repeatLabels" :key="key" :label="label" :value="key" />
                </el-select>
              </el-form-item>
              <el-form-item v-if="scheduleType === 'ONCE'" label="指定日期时间">
                <el-date-picker v-model="onceLocal" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" placeholder="选择未来的日期和时间" />
              </el-form-item>
              <el-form-item v-else label="提醒时间">
                <el-time-select v-model="localTime" start="00:00" step="00:15" end="23:45" placeholder="选择时间" />
              </el-form-item>
              <el-form-item v-if="scheduleType === 'WEEKLY'" label="指定星期">
                <el-checkbox-group v-model="weekdays">
                  <el-checkbox v-for="(name,index) in ['一','二','三','四','五','六','日']" :key="index" :value="index+1">周{{ name }}</el-checkbox>
                </el-checkbox-group>
              </el-form-item>
              <el-form-item v-if="scheduleType === 'MONTHLY'" label="每月几号（31 号按月末处理）">
                <el-input-number v-model="monthDay" :min="1" :max="31" />
              </el-form-item>
              <p class="muted">当前时区：{{ timezone }}。重复提醒按此时区计算。</p>
              <div class="notification-actions">
                <el-button type="primary" :loading="saving" @click="save(false)">保存提醒</el-button>
                <el-button :loading="saving" @click="save(true)">立即发送一次</el-button>
                <el-button v-if="editId !== null" @click="reset">取消编辑</el-button>
              </div>
            </el-form>
          </el-card>
          <div class="notification-side">
            <el-card shadow="never">
              <template #header><strong>通知预览</strong></template>
              <p class="muted">Matrix PRP · {{ notificationCategoryLabel(category) }}</p>
              <h3>{{ currentPreview }}</h3>
              <p>{{ body || '这里会显示你填写的通知正文。' }}</p>
            </el-card>
            <el-card shadow="never">
              <template #header><strong>已创建提醒</strong></template>
              <el-empty v-if="!rules.length" description="还没有提醒规则" />
              <div v-for="rule in rules" :key="rule.id" class="notification-entry">
                <div class="entry-heading"><strong>{{ rule.title }}</strong><el-tag :type="rule.enabled ? 'success' : 'info'">{{ rule.enabled ? '启用' : '暂停' }}</el-tag></div>
                <p>{{ rule.body }}</p>
                <small>{{ repeatLabels[rule.scheduleType] }} · {{ rule.localTime || '单次' }}</small>
                <div class="notification-actions">
                  <el-button size="small" text @click="edit(rule)">编辑</el-button>
                  <el-button size="small" text @click="toggle(rule)">{{ rule.enabled ? '暂停' : '恢复' }}</el-button>
                  <el-button size="small" text type="danger" @click="remove(rule)">删除</el-button>
                </div>
              </div>
            </el-card>
          </div>
        </div>
      </el-tab-pane>
      <el-tab-pane :label="`消息收件箱（${inbox.filter(m => !m.readAt).length}）`" name="inbox">
        <el-card shadow="never">
          <el-empty v-if="!inbox.length" description="还没有收到消息" />
          <div v-for="item in inbox" :key="item.id" class="notification-entry" @click="acknowledge(item)">
            <div class="entry-heading">
              <strong>{{ item.title }}</strong>
              <el-tag v-if="!item.readAt" size="small">未读</el-tag>
            </div>
            <p>{{ item.body }}</p>
            <small>{{ notificationCategoryLabel(item.category) }} · {{ item.createdAt }}</small>
          </div>
        </el-card>
      </el-tab-pane>
      <el-tab-pane label="推送设备" name="devices">
        <el-card shadow="never">
          <h3>系统推送</h3>
          <p class="muted">通知权限：{{ notificationPermissionLabel(permission) }}。iPhone 必须先添加到主屏幕，并从桌面打开 App。</p>
          <p v-if="iosDevice && !standalonePwa" class="push-warning">检测到 iPhone 当前未以主屏幕应用模式运行。Safari 标签页无法完成 iOS Web Push 订阅。</p>
          <p v-if="pushStatus" class="push-diagnostic" role="status">{{ pushStatus }}</p>
          <p v-if="pushNextStep" class="muted push-next-step">下一步：{{ pushNextStep }}</p>
          <div class="notification-actions">
            <el-button type="primary" :loading="subscribing" @click="enablePush">开启当前设备通知</el-button>
            <el-button @click="sendTest">发送测试通知</el-button>
          </div>
          <el-divider />
          <h3>已订阅设备</h3>
          <el-empty v-if="!devices.length" description="还没有绑定推送设备" />
          <div v-for="device in devices" :key="device.id" class="notification-entry entry-heading">
            <span>{{ device.deviceName }}</span><el-button size="small" type="danger" text @click="revokeDevice(device)">移除设备</el-button>
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </AppLayout>
</template>

<style scoped>
.notification-grid { display:grid; grid-template-columns:minmax(0,1.1fr) minmax(0,1fr); gap:18px; }
.notification-side {display:grid; gap:18px; align-content:start;}
.notification-actions {display:flex;flex-wrap:wrap; gap:8px; margin-top:12px;}
.notification-entry {padding:12px 0; border-bottom:1px solid #e5e7eb;cursor:pointer;}
.notification-entry p {margin:7px 0;white-space:pre-wrap;overflow-wrap:anywhere;}
.notification-entry small,.muted {color:#64748b;}

.push-warning {color:#9a3412;background:#fff7ed;border:1px solid #fed7aa;padding:10px 12px;border-radius:8px;}
.push-diagnostic {font-weight:600;overflow-wrap:anywhere;}
.push-next-step {overflow-wrap:anywhere;}
.entry-heading {display:flex;align-items:center;justify-content:space-between;gap:10px;}
@media(max-width:960px){.notification-grid{grid-template-columns:1fr;}}
</style>


