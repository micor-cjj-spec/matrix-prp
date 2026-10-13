import { computed, ref } from 'vue'
import {
  createFolder, deleteFolder, deleteVideo, getFolders, getVideos, renameFolder, updateVideo,
  type VideoFolder, type VideoItem,
} from '@/api/video'

export function useVideoLibrary() {
  const folders = ref<VideoFolder[]>([])
  const videos = ref<VideoItem[]>([])
  const selectedFolderId = ref<number | null>(null)
  const loading = ref(false)
  let requestSerial = 0

  const folderTitle = computed(() => selectedFolderId.value === null ? '全部视频'
    : folders.value.find(folder => folder.id === selectedFolderId.value)?.name ?? '视频学习')
  const orderedVideos = computed(() => [...videos.value]
    .sort((a, b) => a.title.localeCompare(b.title, 'zh-CN', { numeric: true })))
  const flatFolders = computed(() => {
    const result: { folder: VideoFolder; depth: number }[] = []
    const visit = (parentId: number | null, depth: number, seen: Set<number>) => {
      for (const folder of folders.value.filter(item => item.parentId === parentId)) {
        if (seen.has(folder.id)) continue
        result.push({ folder, depth })
        visit(folder.id, depth + 1, new Set([...seen, folder.id]))
      }
    }
    visit(null, 0, new Set())
    return result
  })

  async function loadFolders() { folders.value = await getFolders() }

  async function loadVideos() {
    const serial = ++requestSerial
    const folderId = selectedFolderId.value
    loading.value = true
    try {
      const items = await getVideos(folderId)
      if (serial === requestSerial && folderId === selectedFolderId.value) videos.value = items
    } finally {
      if (serial === requestSerial) loading.value = false
    }
  }
  async function refresh() { await Promise.all([loadFolders(), loadVideos()]) }
  async function selectFolder(id: number | null) {
    if (selectedFolderId.value === id) return
    selectedFolderId.value = id
    videos.value = []
    await loadVideos()
  }
  async function addFolder(name: string) {
    await createFolder(name, selectedFolderId.value)
    await loadFolders()
  }
  async function editFolder(id: number, name: string) {
    await renameFolder(id, name)
    await loadFolders()
  }
  async function removeFolder(id: number) {
    await deleteFolder(id)
    if (selectedFolderId.value === id) {
      selectedFolderId.value = null
      videos.value = []
    }
    await refresh()
  }
  async function editVideo(id: number, title: string, folderId: number | null) {
    await updateVideo(id, title, folderId)
    await loadVideos()
  }
  async function removeVideo(id: number) {
    await deleteVideo(id)
    await loadVideos()
  }
  function dispose() { ++requestSerial }
  return {
    folders, videos, selectedFolderId, loading, folderTitle, orderedVideos, flatFolders,
    refresh, loadFolders, loadVideos, selectFolder, addFolder, editFolder,
    removeFolder, editVideo, removeVideo, dispose,
  }
}
