import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { latestChatToRestore, shouldApplyLoadedConversation } from '../src/utils/chatRestore.ts'

const mostRecent = [{id:'most-recent'}, {id:'older'}]
const blank = {
  selectedId:null, hasMessages:false, isSending:false,
  explicitlyStartedNew:false, hasDraft:false,
}

test('on a fresh visit, reopen latest persisted conversation', () => {
  assert.equal(latestChatToRestore(mostRecent, blank), 'most-recent')
  assert.equal(latestChatToRestore([], blank), null)
})

test('never override explicit new-chat, an existing selection, a draft or streaming reply', () => {
  for (const change of [
    { explicitlyStartedNew:true },
    { selectedId:'older' },
    { hasMessages:true },
    { hasDraft:true },
    { isSending:true },
  ]) assert.equal(latestChatToRestore(mostRecent, {...blank,...change}), null)
})

test('late automatic history response cannot override a new chat, a draft, a send or another selection', () => {
  assert.equal(shouldApplyLoadedConversation(mostRecent, 'most-recent', true, 7, 7, blank), true)
  assert.equal(shouldApplyLoadedConversation(mostRecent, 'most-recent', true, 7, 8, blank), false)
  assert.equal(shouldApplyLoadedConversation(mostRecent, 'most-recent', true, 7, 7, {...blank, explicitlyStartedNew:true}), false)
  assert.equal(shouldApplyLoadedConversation(mostRecent, 'most-recent', true, 7, 7, {...blank, hasDraft:true}), false)
  assert.equal(shouldApplyLoadedConversation(mostRecent, 'most-recent', true, 7, 7, {...blank, isSending:true}), false)
  assert.equal(shouldApplyLoadedConversation(mostRecent, 'most-recent', true, 7, 7, {...blank, selectedId:'older'}), false)
  assert.equal(shouldApplyLoadedConversation(mostRecent, 'older', false, 7, 7, blank), true)
  assert.equal(shouldApplyLoadedConversation(mostRecent, 'older', false, 7, 8, blank), false)
  const view = readFileSync(new URL('../src/views/ChatView.vue', import.meta.url), 'utf8')
  assert.match(view, /const requestId = \+\+activeSelectionRequest/)
  assert.match(view, /shouldApplyLoadedConversation\(/)
  assert.match(view, /if \(!canApply\) return/)
  assert.match(view, /\+\+activeSelectionRequest \/\/ A pending automatic history load/)
})

test('conversation API and usage API failures are handled independently', () => {
  const view = readFileSync(new URL('../src/views/ChatView.vue', import.meta.url), 'utf8')
  assert.match(view, /Promise\.allSettled\(\[listConversations\(\), fetchUsage\(\)\]\)/)
  assert.match(view, /onMounted\(\(\) => \{ void refresh\(true\)/)
  assert.match(view, /historyLoadError/)
  assert.match(view, /重试加载/)
  assert.match(view, /latestChatToRestore\(chats\.value/)
  assert.match(view, /@scroll\.passive="onMessagesScroll"/)
  assert.match(view, /跳到最新消息/)
})

test('mobile chat has definite constrained flex height for touch scrolling', () => {
  const css = readFileSync(new URL('../src/styles/main.css', import.meta.url), 'utf8')
  const section = css.slice(css.lastIndexOf('/* Dedicated immersive chat shell'))
  assert.match(section, /\.prp-shell-chat \{ display:flex; flex-direction:column; height:100dvh/)
  assert.match(section, /\.prp-workspace-chat \{ display:flex; flex:1 1 auto; height:auto; min-height:0/)
  assert.match(section, /\.prp-page-chat \{ flex:1 1 auto; height:auto; min-height:0/)
  const view = readFileSync(new URL('../src/views/ChatView.vue', import.meta.url), 'utf8')
  assert.match(view, /\.prp-chat-messages\{flex:1;min-height:0;overflow-y:auto;-webkit-overflow-scrolling:touch/)
})
