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

test('mobile form inputs do not trigger iOS focus zoom and app viewport stays fixed', () => {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8')
  const css = readFileSync(new URL('../src/styles/main.css', import.meta.url), 'utf8')
  const chat = readFileSync(new URL('../src/views/ChatView.vue', import.meta.url), 'utf8')
  const boot = readFileSync(new URL('../src/main.ts', import.meta.url), 'utf8')
  assert.match(html, /name="viewport" content="[^"]*maximum-scale=1\.0[^"]*user-scalable=no/)
  assert.match(css, /touch-action: pan-x pan-y/)
  assert.match(css, /\.el-textarea__inner[\s\S]*?font-size: 16px !important/)
  assert.match(chat, /:deep\(\.chat-input \.el-textarea__inner\)\{font-size:16px\}/)
  assert.match(boot, /addEventListener\('gesturestart', event => event\.preventDefault\(\)/)
})

test('mobile navigation follows keyboard visibility rather than textarea focus', () => {
  const css = readFileSync(new URL('../src/styles/main.css', import.meta.url), 'utf8')
  const layout = readFileSync(new URL('../src/layouts/AppLayout.vue', import.meta.url), 'utf8')
  assert.doesNotMatch(css, /:has\(\.chat-input textarea:focus\)/)
  assert.match(css, /\.prp-shell-chat\.prp-keyboard-open \.prp-mobile-tabs/)
  assert.match(layout, /window\.visualViewport\?\.addEventListener\('resize', updateKeyboardVisibility\)/)
  assert.match(layout, /@pointerdown="prepareMobileNavigation"/)
  assert.match(layout, /'prp-keyboard-open': activeMain === 'chat' && keyboardVisible/)
})

test('health recording stays inside ordinary chat history, not in a modal', () => {
  const chat = readFileSync(new URL('../src/views/ChatView.vue', import.meta.url), 'utf8')
  const card = readFileSync(new URL('../src/components/ai/WellnessChatCard.vue', import.meta.url), 'utf8')
  const ai = readFileSync(new URL('../src/api/ai.ts', import.meta.url), 'utf8')
  assert.doesNotMatch(chat, /wellnessRecorderVisible|<WellnessAiRecorder/)
  assert.match(chat, /prepareInlineDiet\(content/)
  assert.match(chat, /prepareInlineHealthDraft\(content, selectedId\.value, photo\)/)
  assert.match(chat, /<WellnessChatCard v-else-if="block\.type === 'wellness_draft'"/)
  assert.match(chat, /listMessageBlocks\(result\.conversationId\)/)
  assert.match(chat, /aria-label="添加食物照片"/)
  assert.match(card, /onMounted\(\(\) => \{ void load\(\) \}\)/)
  assert.match(card, /wellnessApi\.searchUsda\(item\.name\)/)
  assert.match(card, /wellnessApi\.importUsda\(selected\.fdcId, alias\)/)
  assert.match(card, /\/wellness\/ai\/drafts\/.*'\/confirm'/)
  assert.match(card, /:disabled="!canConfirm"/)
  assert.match(ai, /type: 'navigation' \| 'wellness_draft'/)
})

test('diet chat backend persists only authorized owner-scoped draft blocks', () => {
  const source = readFileSync(new URL('../../backend/src/main/java/com/matrix/prp/wellness/WellnessAiDraftController.java', import.meta.url), 'utf8')
  const service = readFileSync(new URL('../../backend/src/main/java/com/matrix/prp/wellness/WellnessAiDraftService.java', import.meta.url), 'utf8')
  const store = readFileSync(new URL('../../backend/src/main/java/com/matrix/prp/ai/JdbcAiStore.java', import.meta.url), 'utf8')
  assert.match(source, /!chat\.owns\(user,conversationId\)/)
  assert.match(source, /new AiStore\.MessageBlock\(assistant,"wellness_draft"/)
  assert.match(service, /WHERE id=\? AND user_id=\?/)
  assert.match(store, /"wellness_draft"\.equals\(block\.type\(\)\)/)
})

test('review regressions: explicit food intent, no stale photos, no POST repeat after history failure', () => {
  const chat = readFileSync(new URL('../src/views/ChatView.vue', import.meta.url), 'utf8')
  assert.match(chat, /const directFoodQuantity =/)
  assert.match(chat, /const healthWrite = writeVerb && notTechnicalOrOther/)
  assert.match(chat, /if \(chatPhoto\.value && \(content\.length > 1500/)
  assert.match(chat, /const \[latest, blocks\] = await Promise\.allSettled\(/)
  assert.match(chat, /const localBlock: AiMessageBlock/)
  assert.match(chat, /ElMessage\.warning\('饮食草稿已保存/)
  const card = readFileSync(new URL('../src/components/ai/WellnessChatCard.vue', import.meta.url), 'utf8')
  const api = readFileSync(new URL('../src/api/wellness.ts', import.meta.url), 'utf8')
  assert.match(card, /await wellnessApi\.food\(item\.foodId\)/)
  assert.match(card, /calorieDensity\[i\] = Number\(food\.calories100g\)/)
  assert.match(card, /Number\.isFinite\(calorieDensity\[i\]\)/)
  assert.match(api, /food: \(id: number\) => get<Food>/)
})
