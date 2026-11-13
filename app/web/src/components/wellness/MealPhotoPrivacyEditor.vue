<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { prepareMealPhoto, photoDisposition, paintPrivateMealPhoto, type PhotoRect } from '@/utils/mealPhoto'

/**
 * All operations run locally. The original File is used only for object-URL
 * decoding. Parent components receive the exported, redacted JPEG only.
 */
const props = defineProps<{ source: File }>()
const emit = defineEmits<{ prepared: [file: File]; cancel: [] }>()
const previewCanvas = ref<HTMLCanvasElement | null>(null)
const ready = ref(false)
const processing = ref(false)
const error = ref('')
const mode = ref<'mask' | 'crop'>('mask')
const crop = ref<PhotoRect>({ x: 0, y: 0, width: 1, height: 1 })
const masks = ref<PhotoRect[]>([])
let image: HTMLImageElement | null = null
let url: string | null = null
let revision = 0
let start: { x: number; y: number } | null = null
let current: { x: number; y: number } | null = null

function releaseImage() {
  image = null
  if (url) URL.revokeObjectURL(url)
  url = null
}
watch(() => props.source, async source => {
  const token = ++revision
  releaseImage()
  ready.value = false
  error.value = ''
  crop.value = { x: 0, y: 0, width: 1, height: 1 }
  masks.value = []
  start = null
  current = null
  try {
    photoDisposition(source)
    const localUrl = URL.createObjectURL(source)
    url = localUrl
    const loaded = new Image()
    await new Promise<void>((resolve, reject) => {
      loaded.onload = () => resolve()
      loaded.onerror = () => reject(new Error('无法读取这张图片，请先在系统相册转换为 JPG'))
      loaded.src = localUrl
    })
    if (token !== revision) return
    if (!loaded.naturalWidth || !loaded.naturalHeight ||
        loaded.naturalWidth * loaded.naturalHeight > 60_000_000)
      throw new Error('图片尺寸过大，请先缩小再选择')
    image = loaded
    ready.value = true
    await nextTick()
    render()
  } catch (e) {
    if (token === revision)
      error.value = e instanceof Error ? e.message : '图片本地读取失败'
  }
}, { immediate: true })
onBeforeUnmount(() => { ++revision; releaseImage() })

function render() {
  const canvas = previewCanvas.value
  if (!canvas || !image || !ready.value) return
  const sourceWidth = image.naturalWidth * crop.value.width
  const sourceHeight = image.naturalHeight * crop.value.height
  const scale = Math.min(1, 1100 / Math.max(sourceWidth, sourceHeight))
  canvas.width = Math.max(1, Math.round(sourceWidth * scale))
  canvas.height = Math.max(1, Math.round(sourceHeight * scale))
  const context = canvas.getContext('2d', { alpha: false })
  if (!context) { error.value = '此浏览器不支持图片遮挡画布'; ready.value = false; return }
  paintPrivateMealPhoto(context, image, image.naturalWidth, image.naturalHeight,
    canvas.width, canvas.height, crop.value, masks.value)
  if (start && current) {
    const rect = rectBetween(start, current)
    context.save()
    context.strokeStyle = mode.value === 'crop' ? '#1d4ed8' : '#f97316'
    context.lineWidth = Math.max(2, canvas.width / 350)
    context.setLineDash([8, 5])
    context.strokeRect(rect.x * canvas.width, rect.y * canvas.height,
      rect.width * canvas.width, rect.height * canvas.height)
    context.restore()
  }
}
function point(e: PointerEvent): { x: number; y: number } {
  const bounds = (e.currentTarget as HTMLCanvasElement).getBoundingClientRect()
  const clamp = (n: number) => Math.min(1, Math.max(0, n))
  return { x: clamp((e.clientX - bounds.left) / bounds.width),
    y: clamp((e.clientY - bounds.top) / bounds.height) }
}
function rectBetween(a: { x: number; y: number }, b: { x: number; y: number }): PhotoRect {
  return { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y),
    width: Math.abs(a.x - b.x), height: Math.abs(a.y - b.y) }
}
function startDraw(e: PointerEvent) {
  if (!ready.value || processing.value) return
  e.preventDefault()
  ;(e.currentTarget as HTMLCanvasElement).setPointerCapture(e.pointerId)
  start = point(e)
  current = start
  render()
}
function moveDraw(e: PointerEvent) {
  if (!start) return
  current = point(e)
  render()
}
function endDraw(e: PointerEvent) {
  if (!start) return
  const canvas = e.currentTarget as HTMLCanvasElement
  if (canvas.hasPointerCapture(e.pointerId)) canvas.releasePointerCapture(e.pointerId)
  const box = rectBetween(start, point(e))
  start = null
  current = null
  if (box.width < 0.02 || box.height < 0.02) {
    error.value = '请拖动框选一个足够大的区域'
    render()
    return
  }
  error.value = ''
  if (mode.value === 'mask') {
    if (masks.value.length >= 40) {
      error.value = '最多可遮挡40处；建议先裁剪无关区域'
    } else {
      masks.value.push(box)
    }
  } else {
    // Crop selection is relative to the currently shown image. Existing masks
    // are cleared because their geometry would otherwise refer to old pixels.
    const previous = crop.value
    crop.value = {
      x: previous.x + box.x * previous.width,
      y: previous.y + box.y * previous.height,
      width: previous.width * box.width,
      height: previous.height * box.height,
    }
    masks.value = []
    mode.value = 'mask'
  }
  render()
}
function cancelDraw() {
  start = null
  current = null
  render()
}
function chooseMode(value: 'mask' | 'crop') {
  if (processing.value) return
  mode.value = value
  cancelDraw()
}
function undo() {
  if (processing.value) return
  masks.value.pop()
  render()
}
function reset() {
  if (processing.value) return
  crop.value = { x: 0, y: 0, width: 1, height: 1 }
  masks.value = []
  mode.value = 'mask'
  error.value = ''
  render()
}
async function confirm() {
  if (!ready.value || !image || processing.value) return
  processing.value = true
  error.value = ''
  const token = revision
  try {
    const width = image.naturalWidth * crop.value.width
    const height = image.naturalHeight * crop.value.height
    if (width < 40 || height < 40)
      throw new Error('裁剪区域太小，无法可靠识别食物')
    const scale = Math.min(1, 2048 / Math.max(width, height))
    const result = document.createElement('canvas')
    result.width = Math.max(1, Math.round(width * scale))
    result.height = Math.max(1, Math.round(height * scale))
    const context = result.getContext('2d', { alpha: false })
    if (!context) throw new Error('无法在本机生成脱敏图片')
    // Independent output canvas: NO selection outlines or source EXIF metadata.
    paintPrivateMealPhoto(context, image, image.naturalWidth, image.naturalHeight,
      result.width, result.height, crop.value, masks.value)
    const blob = await new Promise<Blob>((resolve, reject) => result.toBlob(
      value => value ? resolve(value) : reject(new Error('本地图片编码失败')),
      'image/jpeg', 0.9))
    const rendered = new File([blob], 'prp-redacted.jpg', { type: 'image/jpeg' })
    const prepared = await prepareMealPhoto(rendered)
    if (token === revision) emit('prepared', prepared.file)
  } catch (e) {
    if (token === revision)
      error.value = e instanceof Error ? e.message : '图片隐私处理失败'
  } finally {
    if (token === revision) processing.value = false
  }
}
</script>

<template>
  <section class="meal-privacy-editor" aria-label="餐食图片本地隐私检查">
    <p class="explain">
      图片还未发送。请选择<strong>黑块遮挡</strong>，用鼠标或手指框住收货人、电话、地址、订单号、支付信息等；
      也可以选择<strong>裁剪</strong>，只保留食物和必要的菜品文字。
    </p>
    <div class="editor-controls">
      <button type="button" :class="{ active: mode === 'mask' }" :disabled="processing" @click="chooseMode('mask')">
        ■ 黑块遮挡
      </button>
      <button type="button" :class="{ active: mode === 'crop' }" :disabled="processing" @click="chooseMode('crop')">
        <span aria-hidden="true">▣</span> 框选裁剪
      </button>
      <button type="button" :disabled="processing || !masks.length" @click="undo">撤销上一处</button>
      <button type="button" :disabled="processing" @click="reset">重置全部</button>
    </div>
    <p class="hint" role="status">
      {{ mode === 'mask' ? '在图片上拖动矩形，松开后区域将覆盖为不透明黑色。' :
        '拖动框选要保留的部分，松开后裁掉框外内容；此前遮挡区域会被重置。' }}
      已遮挡 {{ masks.length }} 处。
    </p>
    <canvas v-show="ready" ref="previewCanvas" class="image-preview"
      aria-label="本地图片预览画布；拖拽添加黑色遮挡或裁剪"
      @pointerdown="startDraw" @pointermove="moveDraw"
      @pointerup="endDraw" @pointercancel="cancelDraw" />
    <p v-if="!ready && !error" class="hint">正在本机读取图片…</p>
    <p v-if="error" class="editor-error" role="alert">{{ error }}</p>
    <p class="hint">
      这里<strong>不会自动识别或删除所有隐私文字</strong>。请亲自检查未遮挡的每个角落；
      只有点击确认后，处理后的 JPEG 才会交给已选 AI 服务商。
      PRP 不保存原始照片，但第三方模型的数据处理规则仍需另外了解。
    </p>
    <div class="editor-actions">
      <button type="button" :disabled="processing" @click="emit('cancel')">取消，不上传</button>
      <button type="button" class="primary" :disabled="!ready || processing" @click="confirm">
        {{ processing ? '正在本机编码…' : '我已检查，使用处理后的图片' }}
      </button>
    </div>
  </section>
</template>

<style scoped>
.meal-privacy-editor{display:grid;gap:12px;min-width:0;line-height:1.55}
.explain,.hint{margin:0;font-size:13px;color:var(--el-text-color-secondary,#687385)}
.editor-controls,.editor-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.editor-controls button,.editor-actions button{border:1px solid var(--el-border-color,#d1d5db);border-radius:9px;
  padding:8px 12px;background:var(--el-bg-color,#fff);color:var(--el-text-color-primary,#222);cursor:pointer;font-size:13px}
.editor-controls button.active{border-color:#2563eb;color:#1d4ed8;background:#eff6ff}
.editor-controls button:disabled,.editor-actions button:disabled{opacity:.5;cursor:not-allowed}
.editor-actions{justify-content:flex-end}
.editor-actions .primary{background:#1d4ed8;color:#fff;border-color:#1d4ed8}
.image-preview{display:block;width:100%;max-height:min(56vh,620px);height:auto;object-fit:contain;
  border-radius:10px;border:1px solid var(--el-border-color,#ddd);cursor:crosshair;touch-action:none;
  background:#fff}
.editor-error{margin:0;color:var(--el-color-danger,#d33);font-size:13px}
</style>
