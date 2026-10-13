export interface RestorableConversation { id: string }

/** Choose the latest persisted conversation only on the first page entry.
 * Never resurrect old chat while a user is composing a fresh conversation. */
export function latestChatToRestore(
  conversations: readonly RestorableConversation[],
  state: {
    selectedId: string | null
    hasMessages: boolean
    isSending: boolean
    explicitlyStartedNew: boolean
    hasDraft: boolean
  },
): string | null {
  if (state.selectedId || state.hasMessages || state.isSending ||
      state.explicitlyStartedNew || state.hasDraft) return null
  return conversations[0]?.id ?? null
}
