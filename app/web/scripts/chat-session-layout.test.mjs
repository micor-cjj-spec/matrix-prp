import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { latestChatToRestore, shouldApplyLoadedConversation } from '../src/utils/chatRestore.ts'
import { isMealCardRequest } from '../src/utils/mealCardIntent.ts'

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
  assert.match(section, /\.prp-shell-chat \{ position:fixed; inset:0; z-index:10/)
  assert.match(section, /height:var\(--prp-chat-viewport-height,100dvh\)/)
  assert.match(section, /\.prp-shell-chat \.prp-mobile-tabs \{ position:absolute; bottom:0/)
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

test('inline meal capture permits per-event calories without adding a food to USDA/catalog', () => {
  const card = readFileSync(new URL('../src/components/ai/WellnessChatCard.vue', import.meta.url), 'utf8')
  const service = readFileSync(new URL('../../backend/src/main/java/com/matrix/prp/wellness/WellnessService.java', import.meta.url), 'utf8')
  const drafts = readFileSync(new URL('../../backend/src/main/java/com/matrix/prp/wellness/WellnessAiDraftService.java', import.meta.url), 'utf8')
  assert.match(card, /本次自定义热量（不入食品库）/)
  assert.match(card, /v-model\.number="item\.manualCalories"/)
  assert.match(card, /Server owns template lookup; custom snapshots never use the standard food catalog/)
  assert.match(card, /manualCalories: Number\(item\.manualCalories\)/)
  assert.match(drafts, /applyUserCalorieEstimate\(verified,input\)/)
  assert.match(drafts, /case "meal\.create"[\s\S]*?wellness\.addAiMeal/)
  assert.match(service, /public Meal addAiMeal\(/)
  assert.match(service, /VALUES \(\?,NULL,\?,\?,\?,\?,\?,\?,\?\)/)
  assert.match(service, /item\.calories\(\),null,null,null/)
})

test('frequent dish estimates are separate from nutrition reference, with one-step opt-in confirmation', () => {
  const card = readFileSync(new URL('../src/components/ai/WellnessChatCard.vue', import.meta.url), 'utf8')
  const manager = readFileSync(new URL('../src/components/wellness/PersonalDishManager.vue', import.meta.url), 'utf8')
  const backend = readFileSync(new URL('../../backend/src/main/java/com/matrix/prp/wellness/WellnessAiDraftService.java', import.meta.url), 'utf8')
  const migration = readFileSync(new URL('../../backend/src/main/resources/db/migration/V17__wellness_personal_dish_templates.sql', import.meta.url), 'utf8')
  assert.match(card, /同时保存到「我的常吃餐品」/)
  assert.match(card, /wellnessApi\.dishes\(/)
  assert.match(card, /usePersonalDish\(/)
  assert.match(card, /引用个人常吃餐品/)
  assert.match(backend, /wellness\.saveDishTemplate\(/)
  assert.match(backend, /wellness\.ownedDishTemplate\(/)
  assert.match(manager, /wellnessApi\.deleteDish\(/)
  assert.match(migration, /prp_wellness_dish_templates/)
  assert.match(migration, /calories_per_serving/)
  assert.match(migration, /MODIFY protein_g DECIMAL\(10,2\) NULL/)
})


test('diet drafts use long per-write timeouts and verify uncertain saves before allowing retry', () => {
  const card = readFileSync(new URL('../src/components/ai/WellnessChatCard.vue', import.meta.url), 'utf8')
  const api = readFileSync(new URL('../src/api/client.ts', import.meta.url), 'utf8')
  assert.match(api, /timeout: 8000/)
  assert.match(card, /const WRITE_TIMEOUT_MS = 45000/)
  assert.match(card, /apiClient\.patch\([^\n]*corrected, \{ timeout: WRITE_TIMEOUT_MS \}\)/)
  assert.match(card, /'\/confirm',[\s\S]*?\{\}, \{ timeout: WRITE_TIMEOUT_MS \}\)/)
  assert.match(card, /async function refreshSaveOutcome\(/)
  assert.match(card, /freshStatus === 'CONSUMED'\) markSaved\(\)/)
  assert.match(card, /async function handleWriteError\(/)
  assert.match(card, /responseStatus === 408/)
  assert.match(card, /responseStatus >= 500/)
  assert.match(card, /if \(ambiguous \|\| responseStatus === 409\)/)
  assert.match(card, /if \(ambiguous\) \{[\s\S]*?saveOutcomeUnknown\.value = true/)
  assert.match(card, /saveOutcomeUnknown\.value = true/)
  assert.match(card, /const canConfirm = computed\(\(\) => !loading\.value && !saving\.value && !saveOutcomeUnknown\.value/)
  assert.match(card, /检查保存状态（防止重复记录）/)
})

test('diet draft fields fit narrow iPhone widths and display grams inline with the input', () => {
  const card = readFileSync(new URL('../src/components/ai/WellnessChatCard.vue', import.meta.url), 'utf8')
  assert.match(card, /@media\(max-width:600px\)/)
  assert.match(card, /\.health-chat-row\{grid-template-columns:minmax\(0,1fr\)/)
  assert.match(card, /\.health-chat-card input:not\(\[type="checkbox"\]\)/)
  assert.match(card, /\.health-chat-card select\{[\s\S]*?height:44px/)
  assert.match(card, /class="health-chat-number-unit"/)
  assert.match(card, /class="health-chat-unit">g<\/span>/)
  assert.match(card, /\.health-chat-card\{max-width:100%;gap:12px/)
  assert.doesNotMatch(card, /<\/input> g<\/label>/)
})


test('health confirmations use the persisted conversation draft instead of model-generated success text', () => {
  const chat = readFileSync(new URL('../src/views/ChatView.vue', import.meta.url), 'utf8')
  const api = readFileSync(new URL('../src/api/ai.ts', import.meta.url), 'utf8')
  const ctrl = readFileSync(new URL('../../backend/src/main/java/com/matrix/prp/wellness/WellnessAiDraftController.java', import.meta.url), 'utf8')
  const persona = readFileSync(new URL('../../backend/src/main/java/com/matrix/prp/ai/AiPersona.java', import.meta.url), 'utf8')
  assert.match(chat, /explicitConfirm\.test\(content\)/)
  assert.match(chat, /confirmPendingHealthDraft\(conversation, content\)/)
  assert.match(chat, /hasHealthCard/)
  assert.match(chat, /(?:录人)/)
  assert.match(api, /'\/wellness\/ai\/chat\/confirm-pending'/)
  assert.match(ctrl, /service\.confirm\(selected\.draft\(\)\.draftId\(\)\)/)
  assert.match(ctrl, /if\(pending\.size\(\)>1\)/)
  assert.match(ctrl, /ALREADY_SAVED/)
  assert.match(persona, /不得仅凭用户回复“确认保存”/)
})
test('one nutrition preview supports multi-meal all-or-nothing atomic confirmation', () => {
  const card = readFileSync(new URL('../src/components/ai/WellnessChatCard.vue', import.meta.url), 'utf8')
  const service = readFileSync(new URL('../../backend/src/main/java/com/matrix/prp/wellness/WellnessAiDraftService.java', import.meta.url), 'utf8')
  assert.match(card, /draft\.action === 'meal\.create_batch'/)
  assert.match(card, /multiMeals/)
  assert.match(card, /@click="confirmMulti"/)
  assert.match(service, /public Preview prepareBatch\(/)
  assert.match(service, /case "meal\.create_batch" ->/)
  assert.match(service, /SELECT id FROM prp_users WHERE id=\? FOR UPDATE/)
  assert.match(service, /目标日期已有相同餐次/)
  assert.match(service, /status='CONSUMED'/)
})


test('chat meal follow-ups create an owner-scoped editable card rather than a plain assistant claim', () => {
  const view = readFileSync(new URL('../src/views/ChatView.vue', import.meta.url), 'utf8')
  const controller = readFileSync(new URL('../../backend/src/main/java/com/matrix/prp/wellness/WellnessAiDraftController.java', import.meta.url), 'utf8')
  const service = readFileSync(new URL('../../backend/src/main/java/com/matrix/prp/wellness/WellnessAiDraftService.java', import.meta.url), 'utf8')
  const card = readFileSync(new URL('../src/components/ai/WellnessChatCard.vue', import.meta.url), 'utf8')
  assert.match(view, /const contextualMealCard =/)
  assert.match(view, /isMealCardRequest\(content, hasRecentMeal\)/)
  assert.match(view, /healthWrite \|\| contextualMealCard \|\| chatPhoto/)
  assert.match(controller, /chat\.messages\(user,conversationId,null,80\),text/)
  assert.match(service, /public Preview prepareConversationMeal\(/)
  assert.match(service, /"meal\.create",serialize\(payload\)/)
  assert.match(card, /draft\.modelUsed === 'conversation\/estimate-preview'/)
  // The contextual banner must precede the status/action v-if chain;
  // putting it after the CONSUMED v-if turns the editor into an unreachable v-else.
  const notice = card.indexOf('draft.modelUsed ===')
  const consumed = card.indexOf('status === \'CONSUMED\'', card.indexOf('<template>'))
  assert.ok(notice > 0 && consumed > notice)
  assert.match(card, /请确认或修改后再保存/)
})

test('fixed iOS chat viewport never allows body scroll to detach the composer from tab bar', () => {
  const css = readFileSync(new URL('../src/styles/main.css', import.meta.url), 'utf8')
  const layout = readFileSync(new URL('../src/layouts/AppLayout.vue', import.meta.url), 'utf8')
  const chat = readFileSync(new URL('../src/views/ChatView.vue', import.meta.url), 'utf8')
  assert.match(css, /\.prp-shell-chat \{ position:fixed; inset:0/)
  assert.match(css, /\.prp-shell-chat \.prp-mobile-tabs \{ position:absolute; bottom:0/)
  assert.match(layout, /chatViewportHeight\.value = keyboardVisible\.value && viewport/)
  assert.match(layout, /'--prp-chat-viewport-height': chatViewportHeight/)
  assert.match(chat, /\.chat-message-content\{flex:1 1 0;min-width:0/)
  assert.match(chat, /markdown-table-wrap\)\{max-width:100%;width:100%;overflow-x:auto/)
})


test('real multi-turn user card request is routed to the health draft editor', () => {
  assert.equal(isMealCardRequest('帮我创建一下卡片我录入今天的晚餐', true), true)
  assert.equal(isMealCardRequest('帮我创建一下卡片我录入今天的晚餐', false), true)
  assert.equal(isMealCardRequest('生成一下卡片我自己录入', true), true)
  assert.equal(isMealCardRequest('帮我录入一下', true), true)
  assert.equal(isMealCardRequest('帮我录入一下', false), false)
  assert.equal(isMealCardRequest('帮我记录系统日志', true), false)
  assert.equal(isMealCardRequest('给我生成一下晚餐健康记录', false), true)
  assert.equal(isMealCardRequest('怎么设计健康记录卡片组件', true), false)
  assert.equal(isMealCardRequest('帮我记录一条系统日志', true), false)
  assert.equal(isMealCardRequest('生成一下卡片', false), false)
  const controller = readFileSync(new URL('../../backend/src/main/java/com/matrix/prp/wellness/WellnessAiDraftController.java', import.meta.url), 'utf8')
  assert.match(controller, /WellnessChatMealRequest\.isContextualFollowup\(text\)/)
  assert.match(controller, /draft=service\.prepareConversationMeal\(/)
  assert.match(controller, /if\(draft==null\) draft=service\.prepare\(text,image\)/)
  const service = readFileSync(new URL('../../backend/src/main/java/com/matrix/prp/wellness/WellnessAiDraftService.java', import.meta.url), 'utf8')
  assert.match(service, /未识别到有效食物明细/)
})


test('chat distinguishes PRP monthly quota from external provider HTTP 429', () => {
  const chat = readFileSync(new URL('../src/views/ChatView.vue', import.meta.url), 'utf8')
  const backend = readFileSync(new URL('../../backend/src/main/java/com/matrix/prp/ai/AiService.java', import.meta.url), 'utf8')
  assert.match(chat, /data\.quotaSource === 'provider'/)
  assert.match(chat, /服务商返回 HTTP 429/)
  assert.match(chat, /PRP 本月 AI 调用配额已用完/)
  assert.match(backend, /"quotaSource", quotaSource/)
  assert.match(backend, /static String quotaSource\(Exception error\)/)
})
