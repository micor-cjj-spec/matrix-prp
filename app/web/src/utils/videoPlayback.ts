/** Keep autoplay inside the active video's course folder, even in "All videos". */
export function nextVideoInFolder<T extends { id: number; folderId: number | null }>(
  current: T | null,
  playlist: readonly T[],
): T | null {
  if (!current) return null
  const index = playlist.findIndex(video => video.id === current.id)
  if (index < 0) return null
  return playlist.slice(index + 1).find(video => video.folderId === current.folderId) ?? null
}

/**
 * Queue progress writes per video without delaying navigation.
 * A pending write finishes before the newest snapshot is sent, so an older
 * request cannot overwrite a newer position when responses arrive out of order.
 */
export function createVideoProgressQueue(
  persist: (videoId: number, positionSeconds: number, durationSeconds: number) => Promise<unknown>,
) {
  type Snapshot = { positionSeconds: number; durationSeconds: number }
  type Pending = { latest: Snapshot }
  const pending = new Map<number, Pending>()

  async function flush(videoId: number, job: Pending): Promise<void> {
    while (true) {
      const snapshot = job.latest
      try {
        await persist(videoId, snapshot.positionSeconds, snapshot.durationSeconds)
      } catch {
        // Best-effort progress saving. A later playback event can retry.
      }
      if (snapshot === job.latest) {
        pending.delete(videoId)
        return
      }
    }
  }

  return (videoId: number, positionSeconds: number, durationSeconds: number): void => {
    if (!Number.isFinite(positionSeconds) || !Number.isFinite(durationSeconds)
      || positionSeconds < 0 || durationSeconds < 0) return

    const snapshot = { positionSeconds, durationSeconds }
    const existing = pending.get(videoId)
    if (existing) {
      existing.latest = snapshot
      return
    }
    const job: Pending = { latest: snapshot }
    pending.set(videoId, job)
    void flush(videoId, job)
  }
}
