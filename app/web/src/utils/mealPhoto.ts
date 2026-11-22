/** Food photos are resized locally before crossing the existing 3 MB AI upload limit. */
export const AI_PHOTO_MAX_BYTES = 3_000_000
export const AI_PHOTO_TARGET_BYTES = 2_600_000
export const AI_PHOTO_MAX_SOURCE_BYTES = 25_000_000

const DIRECT_MIMES = new Set(['image/jpeg', 'image/png', 'image/webp'])
const CONVERT_MIMES = new Set(['image/heic', 'image/heif'])
const ALL_MIMES = new Set([...DIRECT_MIMES, ...CONVERT_MIMES])
type PhotoLike = Pick<File, 'name' | 'size' | 'type'>
type Disposition = 'convert'

function mimeOf(file: PhotoLike): string {
  if (ALL_MIMES.has(file.type.toLowerCase())) return file.type.toLowerCase()
  if (file.type) return ''
  const suffix = file.name.split('.').pop()?.toLowerCase()
  const aliases: Record<string, string> = {
    jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png',
    webp: 'image/webp', heic: 'image/heic', heif: 'image/heif',
  }
  return suffix ? aliases[suffix] ?? '' : ''
}

export function photoDisposition(file: PhotoLike): Disposition {
  if (!ALL_MIMES.has(mimeOf(file)))
    throw new Error('请选择 JPG、PNG、WebP 或 HEIC/HEIF 格式的照片')
  if (file.size < 1) throw new Error('照片为空，请重新选择')
  if (file.size > AI_PHOTO_MAX_SOURCE_BYTES)
    throw new Error('原始照片超过 25 MB，请先在相册中缩小图片后重试')
  // Always redraw, even small JPG/PNG/WebP. Passing the original can leak
  // EXIF/GPS, original filenames and other embedded metadata to the model.
  return 'convert'
}

export function scaledPhotoDimensions(width: number, height: number, maxEdge: number): { width: number; height: number } {
  if (![width, height, maxEdge].every(Number.isFinite) || width <= 0 || height <= 0 || maxEdge <= 0)
    throw new Error('图片尺寸无效')
  const scale = Math.min(1, maxEdge / Math.max(width, height))
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) }
}

/**
 * Normalized rectangles are local canvas geometry, never sent as metadata.
 * The actual outgoing JPEG must be rendered from this canvas after both crop
 * and irreversible opaque black masks are applied.
 */
export interface PhotoRect { x: number; y: number; width: number; height: number }
type PrivacyCanvas = Pick<CanvasRenderingContext2D, 'fillRect' | 'drawImage' | 'fillStyle'>
function validRect(r: PhotoRect): boolean {
  return [r.x, r.y, r.width, r.height].every(Number.isFinite) &&
    r.x >= 0 && r.y >= 0 && r.width > 0 && r.height > 0 &&
    r.x + r.width <= 1.0000001 && r.y + r.height <= 1.0000001
}
/**
 * Shared by the preview and the file encoder; crop drops pixels outside the
 * selected region, and masks replace pixels with solid BLACK, not blur.
 */
/**
 * When cropping after masking, transform the still-visible portions of all
 * existing masks into the newly cropped image. Never silently drop protection.
 */
export function remapPrivateMealMasks(crop: PhotoRect, masks: readonly PhotoRect[]): PhotoRect[] {
  if (!validRect(crop) || masks.length > 40 || masks.some(m => !validRect(m)))
    throw new Error('图片裁剪或遮挡区域无效')
  const mapped: PhotoRect[] = []
  for (const mask of masks) {
    const left = Math.max(crop.x, mask.x)
    const top = Math.max(crop.y, mask.y)
    const right = Math.min(crop.x + crop.width, mask.x + mask.width)
    const bottom = Math.min(crop.y + crop.height, mask.y + mask.height)
    if (right <= left || bottom <= top) continue
    mapped.push({
      x: Math.max(0, (left - crop.x) / crop.width),
      y: Math.max(0, (top - crop.y) / crop.height),
      width: (right - left) / crop.width,
      height: (bottom - top) / crop.height,
    })
  }
  return mapped
}

export function paintPrivateMealPhoto(
  context: PrivacyCanvas, image: CanvasImageSource,
  sourceWidth: number, sourceHeight: number,
  width: number, height: number,
  crop: PhotoRect, masks: readonly PhotoRect[],
): void {
  if (![sourceWidth, sourceHeight, width, height].every(x => Number.isFinite(x) && x > 0) ||
      !validRect(crop) || masks.length > 40 || masks.some(m => !validRect(m)))
    throw new Error('图片裁剪或遮挡区域无效')
  context.fillStyle = '#ffffff'
  context.fillRect(0, 0, width, height)
  context.drawImage(image,
    crop.x * sourceWidth, crop.y * sourceHeight,
    crop.width * sourceWidth, crop.height * sourceHeight,
    0, 0, width, height)
  context.fillStyle = '#000000'
  for (const mask of masks) {
    // Snap outward to whole pixels and pad two pixels to survive resizing and
    // JPEG ringing at the edges: NEVER blur or partially cover private text.
    const x1 = Math.max(0, Math.floor(mask.x * width) - 2)
    const y1 = Math.max(0, Math.floor(mask.y * height) - 2)
    const x2 = Math.min(width, Math.ceil((mask.x + mask.width) * width) + 2)
    const y2 = Math.min(height, Math.ceil((mask.y + mask.height) * height) + 2)
    context.fillRect(x1, y1, x2 - x1, y2 - y1)
  }
}

export interface PreparedMealPhoto { file: File; compressed: boolean; originalBytes: number }

/**
 * Always canvas-redraw before upload: even <=3 MB originals can contain
 * EXIF/GPS. The output contains only re-encoded pixels and a generic filename.
 * No persistent storage, original upload or third-party JavaScript.
 */
export async function prepareMealPhoto(source: File): Promise<PreparedMealPhoto> {
  photoDisposition(source)

  const objectUrl = URL.createObjectURL(source)
  const image = new Image()
  try {
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve()
      image.onerror = () => reject(new Error('浏览器无法读取这张照片，请在相册中转为 JPEG 后再试'))
      image.src = objectUrl
    })
    const width = image.naturalWidth, height = image.naturalHeight
    if (width <= 0 || height <= 0 || width * height > 60_000_000)
      throw new Error('图片尺寸无效或像素过大，请先缩小后重试')
    const canvas = document.createElement('canvas')
    const context = canvas.getContext('2d', { alpha: false })
    if (!context) throw new Error('此浏览器不支持图片压缩，请使用 JPG 照片')
    let smallest: Blob | null = null
    for (const edge of [2048, 1760, 1536, 1280, 1024, 800]) {
      const dimensions = scaledPhotoDimensions(width, height, edge)
      canvas.width = dimensions.width
      canvas.height = dimensions.height
      context.fillStyle = '#ffffff'
      context.fillRect(0, 0, canvas.width, canvas.height)
      context.drawImage(image, 0, 0, canvas.width, canvas.height)
      for (const quality of [0.88, 0.76, 0.64, 0.52]) {
        const blob = await new Promise<Blob>((resolve, reject) => {
          canvas.toBlob(result => result ? resolve(result) :
            reject(new Error('图片压缩失败，请重新选择')), 'image/jpeg', quality)
        })
        if (!smallest || blob.size < smallest.size) smallest = blob
        if (blob.size <= AI_PHOTO_TARGET_BYTES) {
          return {
            file: new File([blob], 'prp-meal.jpg', { type: 'image/jpeg', lastModified: Date.now() }),
            compressed: true,
            originalBytes: source.size,
          }
        }
      }
    }
    if (smallest && smallest.size <= AI_PHOTO_MAX_BYTES) {
      return {
        file: new File([smallest], 'prp-meal.jpg', { type: 'image/jpeg', lastModified: Date.now() }),
        compressed: true,
        originalBytes: source.size,
      }
    }
    throw new Error('照片压缩后仍超过 3 MB，请换一张照片')
  } finally {
    image.onload = null
    image.onerror = null
    URL.revokeObjectURL(objectUrl)
  }
}

export function photoSizeLabel(bytes: number): string {
  return (bytes / 1_000_000).toFixed(2) + ' MB'
}
