import type { TaskItem } from '../api/tasks'

export type TaskSortOrder = 'recommended' | 'due' | 'recent'

export interface TaskListControls {
  today: string
  quickFilter?: string
  keyword?: string
  sortBy?: TaskSortOrder
  status?: string
  moduleCode?: string
  priority?: string
  dueDate?: string
}

export interface TaskProgress {
  total: number
  done: number
  inProgress: number
  todo: number
  percent: number
}

export interface ModuleTaskProgress extends TaskProgress {
  moduleCode: string
}

function isOpen(task: TaskItem): boolean {
  return task.status !== 'done' && task.status !== 'canceled'
}

const priorityWeight: Record<string, number> = { high: 0, medium: 1, low: 2 }

function recommendedWeight(task: TaskItem, today: string): number {
  if (task.status === 'canceled') return 7
  if (task.status === 'done') return 6
  if (task.status === 'in_progress') return 0
  if (task.dueDate && task.dueDate < today) return 1
  if (task.dueDate === today) return 2
  if (task.priority === 'high') return 3
  if (task.dueDate) return 4
  return 5
}

function compareDue(a: TaskItem, b: TaskItem): number {
  // Unscheduled items are last; valid API dates use ISO yyyy-MM-dd.
  return (a.dueDate || '9999-12-31').localeCompare(b.dueDate || '9999-12-31')
}

export function filterAndRankTasks(tasks: readonly TaskItem[], options: TaskListControls): TaskItem[] {
  const { today, quickFilter = 'all', sortBy = 'recommended' } = options
  const keyword = (options.keyword || '').trim().toLocaleLowerCase()
  return tasks.filter(task => {
    if (options.status && task.status !== options.status) return false
    if (options.moduleCode && task.moduleCode !== options.moduleCode) return false
    if (options.priority && task.priority !== options.priority) return false
    if (options.dueDate && task.dueDate !== options.dueDate) return false
    if (keyword && !(task.title + ' ' + (task.description || '')).toLocaleLowerCase().includes(keyword)) return false
    if (quickFilter === 'active') return task.status === 'in_progress'
    if (quickFilter === 'todo') return task.status === 'todo'
    if (quickFilter === 'all') return true
    if (!isOpen(task)) return false
    if (quickFilter === 'today') return task.dueDate === today
    if (quickFilter === 'overdue') return !!task.dueDate && task.dueDate < today
    if (quickFilter === 'unscheduled') return !task.dueDate
    if (quickFilter === 'future') return !!task.dueDate && task.dueDate > today
    return true
  }).sort((a, b) => {
    if (sortBy === 'recent') {
      return (b.createdAt || '').localeCompare(a.createdAt || '') || b.id - a.id
    }
    if (sortBy === 'due') {
      const terminal = Number(!isOpen(a)) - Number(!isOpen(b))
      if (terminal) return terminal
      // Completed tasks precede canceled tasks when both are terminal.
      if (!isOpen(a) && !isOpen(b)) {
        const canceled = Number(a.status === 'canceled') - Number(b.status === 'canceled')
        if (canceled) return canceled
      }
      const due = compareDue(a, b)
      if (due) return due
    } else {
      const rank = recommendedWeight(a, today) - recommendedWeight(b, today)
      if (rank) return rank
    }
    const priority = (priorityWeight[a.priority] ?? 3) - (priorityWeight[b.priority] ?? 3)
    if (priority) return priority
    return compareDue(a, b) || b.id - a.id
  })
}

export function getNextTask(tasks: readonly TaskItem[], today: string): TaskItem | null {
  return filterAndRankTasks(tasks.filter(isOpen), { today })[0] ?? null
}

export function taskProgress(tasks: readonly TaskItem[]): TaskProgress {
  const remaining = tasks.filter(task => task.status !== 'canceled')
  const done = remaining.filter(task => task.status === 'done').length
  const inProgress = remaining.filter(task => task.status === 'in_progress').length
  const todo = remaining.filter(task => task.status === 'todo').length
  const total = remaining.length
  return { total, done, inProgress, todo, percent: total ? Math.round(done * 100 / total) : 0 }
}

export function moduleTaskProgress(tasks: readonly TaskItem[]): ModuleTaskProgress[] {
  const byModule = new Map<string, TaskItem[]>()
  for (const task of tasks) {
    if (task.status === 'canceled') continue
    const bucket = byModule.get(task.moduleCode) ?? []
    bucket.push(task)
    byModule.set(task.moduleCode, bucket)
  }
  return [...byModule.entries()].map(([moduleCode, items]) =>
    ({ moduleCode, ...taskProgress(items) })
  ).sort((a, b) =>
    (b.todo + b.inProgress) - (a.todo + a.inProgress) ||
    a.moduleCode.localeCompare(b.moduleCode)
  )
}
