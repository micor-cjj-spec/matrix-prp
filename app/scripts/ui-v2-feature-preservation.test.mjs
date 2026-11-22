import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

// Functional-structure contract for purely visual PRP UI V2 refactors.
// Keeping this source-level test small makes it easy to review with each redesign.
const appDir = join(dirname(fileURLToPath(import.meta.url)), '..')
const source = path => readFileSync(join(appDir, path), 'utf8')
const layout = source('web/src/layouts/AppLayout.vue')
const router = source('web/src/router/index.ts')
const home = source('web/src/views/DashboardView.vue')
const apps = source('web/src/views/AppsView.vue')
const learning = source('web/src/views/LearningView.vue')
const wellness = source('web/src/views/WellnessView.vue')
const chat = source('web/src/views/ChatView.vue')
const me = source('web/src/views/MeView.vue')
const entry = source('web/src/main.ts')
const theme = source('web/src/styles/quiet-intelligence-v2.css')
const modulesTheme = source('web/src/styles/quiet-intelligence-modules-v2.css')
const uniPages = JSON.parse(source('mobile/src/pages.json'))
const mobileVideo = source('mobile/src/pages/video/index.vue')
const mobileAi = source('mobile/src/pages/ai/index.vue')

function assertEvery(text, fragments, context) {
  for (const fragment of fragments) assert.ok(text.includes(fragment), context + ': missing ' + fragment)
}

test('UI V2 is activated and preserves all four first-level destinations', () => {
  assert.ok(entry.includes("import './styles/quiet-intelligence-v2.css'"))
  const entries = [...layout.matchAll(/\{ code: '(home|apps|chat|me)', label: '([^']+)', to: '([^']+)'/g)]
  assert.deepEqual(entries.map(x => [x[1], x[3]]), [['home','/'],['apps','/apps'],['chat','/chat'],['me','/me']])
  assertEvery(layout, ['class="nav-list prp-main-nav"', 'class="prp-mobile-tabs"', 'v-for="item in mainNav"', '@pointerdown="prepareMobileNavigation"'], 'main navigation')
  assertEvery(router, ["path: '/learning'", "path: '/wellness'", "path: '/practice'", "path: '/videos'", "path: '/finance'", "path: '/life'", "path: '/tasks'", "path: '/records'"], 'domain routes')
})

test('all home entry links and task completion behavior remain accessible', () => {
  assertEvery(home, ['to="/tasks"', 'to="/learning"', 'to="/wellness"', 'to="/finance"', 'to="/life"', 'to="/videos"', 'to="/records"', 'to="/chat"', 'completeTask(task.id)', 'completeTask(todoItems[0].id)', 'pendingTask === todoItems[0].id', 'onMounted(refresh)'], 'home')
})

test('app directory still offers search, categories, favorites, and dynamic registry', () => {
  assertEvery(apps, ['getAppEntries', 'groupOrder', 'v-for="item in section.items"', 'groupedEntries', 'groupDescriptions', 'v-for="section in groupedEntries"', 'v-for="group in categories"', 'v-model="query"', 'toggleFavorite(item.code)', 'localStorage.setItem', 'groupNames'], 'app catalog')
})

test('health workflows retain all six tabs, actions and authorization-aware AI changes', () => {
  for (const tab of ['ai','today','meals','exercise','metrics','goals'])
    assert.ok(wellness.includes('name="' + tab + '"'), 'missing health tab ' + tab)
  assertEvery(wellness, [
    '<WellnessAiRecorder', 'openMeal()', 'openExercise()', 'openMetric()',
    'openAiChange(', 'copyMeal(meal)', 'deleteMeal(meal)', 'saveMeal()',
    'saveGoal()', 'saveProfile()', 'openUsda()', 'saveFood()', 'loadTrend()'
  ], 'health actions')
})

test('learning module retains videos, practice, vocal, notes, knowledge and review', () => {
  assertEvery(learning, ['to="/videos"', 'to="/practice"', 'to="/vocal"', 'to="/records"', 'to="/knowledge"', 'to="/tasks"', 'to="/reviews"', 'canOpenKnowledge'], 'learning')
})

test('chat and me retain critical controls, consent and owner settings', () => {
  assertEvery(chat, ['<ChatConversationPanel', 'historyOpen', 'newChat', 'changeProvider', 'changeModel', 'photoSelected', 'send()', 'confirmShare', 'selectedScopes', 'streamChat'], 'chat')
  assertEvery(me, ["'/me/ai-settings'", "'/me/mcp-clients'", "'/notifications'", "'/me/settings'", "'/me/guide'", "'/me/about'", 'to="/me/agent-tasks"', 'to="/me/codex-jobs"', 'v-if="auth.user?.administrator"', 'inviteFriend', 'logout'], 'me')
})

test('mobile chat viewport and original iOS keyboard behavior stay intact', () => {
  assertEvery(layout, ['visualViewport', 'prepareMobileNavigation', 'prp-keyboard-open', '--prp-chat-viewport-height'], 'chat viewport')
  assertEvery(theme, [
    '.prp-shell.prp-shell-chat {',
    'height:var(--prp-chat-viewport-height,100dvh)',
    '.prp-shell.prp-shell-chat .prp-workspace-chat',
    '.prp-shell.prp-shell-chat.prp-keyboard-open .prp-mobile-tabs {display:none}'
  ], 'responsive chat theme')
})

test('v2 module styling loads and preserves the complete uni-app page registry', () => {
  assert.ok(entry.includes("import './styles/quiet-intelligence-modules-v2.css'"))
  assert.ok(modulesTheme.includes('.chat-conversation-panel'))
  assert.ok(modulesTheme.includes('.tasks-module-item'))
  assert.ok(modulesTheme.includes('.study-playlist'))
  assert.deepEqual(uniPages.pages.map(page => page.path), [
    'pages/login/index', 'pages/home/index', 'pages/record/index',
    'pages/task/index', 'pages/finance/index', 'pages/video/index','pages/ai/index'
  ])
  assert.equal(uniPages.globalStyle.backgroundColor, '#f7f8f4')
})

test('module pages provide back-to-apps affordance, without replacing the main nav', () => {
  assertEvery(layout, ['class="prp-back-to-apps"', 'route.path !== \'/apps\'', 'to="/apps"', 'class="nav-list prp-main-nav"'], 'app breadcrumb')
})


test('category grouping has a one-to-one source without dropping search or favorites', () => {
  assertEvery(apps, [
    'groupOrder', 'groupedEntries', 'items: filtered.value.filter(item => item.group === group)',
    'v-for="section in groupedEntries"', 'v-for="item in section.items"',
    'groupNames[section.group]', 'filtered.length', 'v-model="query"',
    'v-for="group in categories"', 'toggleFavorite(item.code)', ':to="item.route"'
  ], 'grouped app directory')
})


test('native mobile video and AI interactions remain available after visual updates', () => {
  assertEvery(mobileVideo, [
    'selectFolder(', 'changeSpeed(', 'persistProgress', 'onVideoEnded',
    'video-player-mobile', 'video-speed-button', 'v-for="entry in flatFolders"'
  ], 'mobile video')
  assertEvery(mobileAi, [
    'newChat', 'openConversation(', 'send', 'chat-messages',
    'chat-bubble', 'chat-input', 'history-button'
  ], 'mobile AI')
})
