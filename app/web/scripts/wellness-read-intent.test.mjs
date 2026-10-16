import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { isWellnessReadQuery } from '../src/utils/wellnessReadIntent.ts'

test('meal record gap questions request one-time wellness consent', () => {
  for (const phrase of [
    '帮我查一下，我有哪几次的用餐情况没有录入',
    '查一下近30天哪些午餐没记录',
    '统计一下过去两周晚饭哪些没有录入',
    '查询最近的饮食记录',
  ]) assert.equal(isWellnessReadQuery(phrase), true, phrase)
  const view = readFileSync(new URL('../src/views/ChatView.vue', import.meta.url), 'utf8')
  assert.match(view, /isWellnessReadQuery\(content\)/)
  assert.match(view, /selectedScopes\.value = \['wellness'\]/)
  assert.match(view, /await showPreview\(\)/)
  assert.ok(view.indexOf('isWellnessReadQuery(content)') < view.indexOf('const writeVerb ='))
})

test('writing meals and technical questions do not trigger read permissions', () => {
  for (const phrase of [
    '帮我记录今天午餐吃的鸡腿饭',
    '请帮我新增一份早餐',
    '我想让你直接保存今天的饮食',
    '怎么开发一个饮食记录页面',
    '早饭是一杯牛奶和鸡蛋',
  ]) assert.equal(isWellnessReadQuery(phrase), false, phrase)
})
