/** Food photos are resized locally before crossing the existing 3 MB AI upload limit. */
export const AI_PHOTO_MAX_BYTES = 3_000_000
export const AI_PHOTO_TARGET_BYTES = 2_600_000
export const AI_PHOTO_MAX_SOURCE_BYTES = 25_000_000

const DIRECT_MIMES = new Set(['image/jpeg', 'image/png', 'image/webp'])
const CONVERT_MIMES = new Set(['image/heic', 'image/heif'])
const ALL_MIMES = new Set([...DIRECT_MIMES, ...CONVERT_MIMES])
type PhotoLike = Pick<File, 'name' | 'size' | 'type'>
type Disposition = 'keep' | 'convert'

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
  if (DIRECT_MIMES.has(mimeOf(file)) && file.size <= AI_PHOTO_MAX_BYTES) return 'keep'
  return 'convert'
}

export function scaledPhotoDimensions(width: number, height: number, maxEdge: number): { width: number; height: number } {
  if (![width, height, maxEdge].every(Number.isFinite) || width <= 0 || height <= 0 || maxEdge <= 0)
    throw new Error('图片尺寸无效')
  const scale = Math.min(1, maxEdge / Math.max(width, height))
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) }
}

export interface PreparedMealPhoto { file: File; compressed: boolean; originalBytes: number }

/**
 * Canvas-based conversion keeps the actual POST below 3,000,000 bytes, without
 * uploading the original image or retaining EXIF/GPS metadata. No third-party JS.
 */
export async function prepareMealPhoto(source: File): Promise<PreparedMealPhoto> {
  const disposition = photoDisposition(source)
  if (disposition === 'keep') return { file: source, compressed: false, originalBytes: source.size }

  const objectUrl = URL.createObjectURL(source)
  const image = new Image()
  try {
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve()
      image.onerror = () => reject(new Error('浏览器无法读取这张照片，请在相册中转为 JPEG 后再试'))
      image.src = objectUrl
    })
    const width = image.naturalWidth, height = image.naturalHeight
    if (width <= 0 || height <= 0) throw new Error('图片尺寸无效')
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
          const base = source.name.replace(/\.[^.]+$/, '').slice(0, 80) || 'food'
          return {
            file: new File([blob], base + '-prp.jpg', { type: 'image/jpeg', lastModified: Date.now() }),
            compressed: true,
            originalBytes: source.size,
          }
        }
      }
    }
    if (smallest && smallest.size <= AI_PHOTO_MAX_BYTES) {
      const base = source.name.replace(/\.[^.]+$/, '').slice(0, 80) || 'food'
      return {
        file: new File([smallest], base + '-prp.jpg', { type: 'image/jpeg', lastModified: Date.now() }),
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
