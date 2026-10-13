import { computed, ref } from 'vue'
import { getStorageUsage, uploadVideo, type StorageUsage, type VideoItem } from '@/api/video'

export function useVideoUpload() {
  const usage = ref<StorageUsage | null>(null)
  const uploading = ref(false)
  const uploadPercent = ref(0)
  const fileName = ref('')
  const usagePercent = computed(() => usage.value?.quotaBytes
    ? Math.min(100, Math.round(usage.value.bytesUsed / usage.value.quotaBytes * 100)) : 0)

  async function refreshUsage() { usage.value = await getStorageUsage() }
  async function upload(file: File, folderId: number | null): Promise<VideoItem> {
    if (uploading.value) throw new Error('另一个视频正在上传')
    fileName.value = file.name
    uploadPercent.value = 0
    uploading.value = true
    try {
      const result = await uploadVideo(file, folderId, percent => { uploadPercent.value = percent })
      await refreshUsage()
      return result
    } finally { uploading.value = false }
  }
  return { usage, uploading, uploadPercent, fileName, usagePercent, refreshUsage, upload }
}
