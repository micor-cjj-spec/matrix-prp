import test from 'node:test'
import { loadTaskResources } from '../src/utils/taskLoading.ts'
import assert from 'node:assert/strict'
import {
  filterAndRankTasks, getNextTask, taskProgress, moduleTaskProgress,
} from '../src/utils/taskPlanning.ts'

const today = '2026-11-13'
const mk = (id, overrides = {}) => ({
  id, moduleCode: 'work', title: '任务 ' + id, description: '',
  priority: 'medium', status: 'todo', dueDate: null,
  createdAt: '2026-11-' + String(id).padStart(2, '0') + 'T10:00:00+08:00',
  completedAt: null, ...overrides,
})
const sample = [
  mk(1, { title:'高优先级',priority:'high',moduleCode:'learning' }),
  mk(2, { title:'已逾期',dueDate:'2026-11-11' }),
  mk(3, { title:'今天到期',dueDate:today }),
  mk(4, { title:'正在进行',status:'in_progress' }),
  mk(5, { title:'已完成',status:'done' }),
  mk(6, { title:'已取消',status:'canceled' }),
  mk(7, { title:'以后处理',dueDate:'2026-11-20',description:'PRP 健康模块' }),
]
test('recommended order gives active, overdue, today, high priority, future and terminal tasks', () => {
  const result = filterAndRankTasks(sample, { today })
  assert.deepEqual(result.map(t => t.id), [4,2,3,1,7,5,6])
  assert.equal(getNextTask(sample,today)?.id,4)
  assert.equal(sample[0].id,1, 'input remains unchanged')
})
test('instant quick filters exclude completed/canceled from actionable categories', () => {
  const ids = quickFilter => filterAndRankTasks(sample,{today,quickFilter}).map(t=>t.id)
  assert.deepEqual(ids('active'),[4])
  assert.deepEqual(ids('todo'),[2,3,1,7])
  assert.deepEqual(ids('today'),[3])
  assert.deepEqual(ids('overdue'),[2])
  assert.deepEqual(ids('unscheduled'),[4,1])
  assert.deepEqual(ids('future'),[7])
})
test('search, module and status filters compose without extra server calls', () => {
  assert.deepEqual(filterAndRankTasks(sample,{today,keyword:'健康'}).map(t=>t.id),[7])
  assert.deepEqual(filterAndRankTasks(sample,{today,moduleCode:'learning',priority:'high'}).map(t=>t.id),[1])
  assert.deepEqual(filterAndRankTasks(sample,{today,status:'done'}).map(t=>t.id),[5])
  assert.deepEqual(filterAndRankTasks(sample,{today,quickFilter:'all',dueDate:today}).map(t=>t.id),[3])
})
test('date and newest sorting use deterministic tie breakers', () => {
  assert.deepEqual(filterAndRankTasks(sample,{today,sortBy:'due'}).map(t=>t.id),[2,3,7,1,4,5,6])
  assert.deepEqual(filterAndRankTasks(sample,{today,sortBy:'recent'}).map(t=>t.id),[7,6,5,4,3,2,1])
  assert.deepEqual(filterAndRankTasks([mk(1),mk(2,{createdAt:'2026-11-01T10:00:00+08:00'})],{today,sortBy:'recent'}).map(t=>t.id),[2,1])
})
test('progress excludes canceled tasks and handles an empty list', () => {
  assert.deepEqual(taskProgress(sample),{total:6,done:1,inProgress:1,todo:4,percent:17})
  assert.deepEqual(taskProgress([]),{total:0,done:0,inProgress:0,todo:0,percent:0})
  assert.deepEqual(taskProgress([mk(1,{status:'canceled'})]),{total:0,done:0,inProgress:0,todo:0,percent:0})
})
test('module progress is scoped to task records, excluding canceled tasks', () => {
  assert.deepEqual(moduleTaskProgress(sample).map(m=>[m.moduleCode,m.total,m.done,m.inProgress]),[
    ['work',5,1,1],['learning',1,0,0],
  ])
})

test('task view resource loader preserves tasks when optional summary request fails', async () => {
  const tasks = [mk(1)]
  const modules = [{ code: 'work', name: '工作' }]
  const result = await loadTaskResources(
    async () => tasks,
    async () => { throw new Error('summary service unavailable') },
    async () => modules,
  )
  assert.deepEqual(result.taskItems, tasks)
  assert.equal(result.summaryResult.status, 'rejected')
  assert.deepEqual(result.moduleResult, { status: 'fulfilled', value: modules })
})

test('task view resource loader preserves tasks when optional module request fails', async () => {
  const tasks = [mk(2)]
  const summary = { openCount: 1 }
  const result = await loadTaskResources(
    async () => tasks,
    async () => summary,
    async () => { throw new Error('module directory unavailable') },
  )
  assert.deepEqual(result.taskItems, tasks)
  assert.deepEqual(result.summaryResult, { status: 'fulfilled', value: summary })
  assert.equal(result.moduleResult.status, 'rejected')
})

test('task view resource loader tolerates simultaneous optional failures', async () => {
  const result = await loadTaskResources(
    async () => [mk(3)],
    async () => { throw new Error('summary unavailable') },
    async () => { throw new Error('modules unavailable') },
  )
  assert.equal(result.taskItems.length, 1)
  assert.equal(result.summaryResult.status, 'rejected')
  assert.equal(result.moduleResult.status, 'rejected')
})

test('task view resource loader rejects when the task list itself fails', async () => {
  await assert.rejects(loadTaskResources(
    async () => { throw new Error('task API unavailable') },
    async () => ({ openCount: 0 }),
    async () => [{ code: 'work' }],
  ), /task API unavailable/)
})
