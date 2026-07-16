#!/usr/bin/env node
import { Command } from 'commander'
import { getConfigPath, loadConfig, saveConfig } from './config.js'
import { printItems, printJson } from './format.js'
import { request } from './client.js'
import type {
  DashboardSummary,
  FinanceAccountItem,
  FinanceAccountSummary,
  FinanceCategoryItem,
  FinanceCategorySummary,
  FinanceMonthlySummary,
  FinanceTransactionItem,
  HealthStatus,
  KnowledgeFile,
  KnowledgeNode,
  KnowledgeSearchResult,
  KnowledgeStats,
  LoginResponse,
  ModuleItem,
  RecordItem,
  ReviewItem,
  RuntimeHealth,
  TagItem,
  TaskItem,
  TaskSummary,
  UserProfile,
} from './types.js'

const program = new Command()

program
  .name('matrix-prp')
  .description('CLI for Matrix PRP personal resource planning')
  .version('0.0.1')

program
  .command('config')
  .description('Show CLI configuration')
  .action(async () => {
    const config = await loadConfig()
    printJson({ ...config, token: config.token ? '<saved>' : undefined, path: getConfigPath() })
  })

program
  .command('health')
  .description('Check backend health')
  .action(async () => {
    const [health, runtime] = await Promise.all([
      request<HealthStatus>('get', '/health'),
      request<RuntimeHealth>('get', '/health/runtime'),
    ])
    printJson({ health, runtime })
  })

program
  .command('login')
  .description('Login and save JWT token')
  .option('-u, --username <username>', 'username', 'admin')
  .option('-p, --password <password>', 'password', 'matrix-prp')
  .option('--api <url>', 'API base URL, such as http://localhost:8080/api')
  .action(async (options: { username: string; password: string; api?: string }) => {
    const current = await loadConfig()
    const apiBaseUrl = options.api ?? current.apiBaseUrl
    const response = await request<LoginResponse>(
      'post',
      '/auth/login',
      { username: options.username, password: options.password },
      undefined,
      apiBaseUrl,
    )
    await saveConfig({ apiBaseUrl, token: response.token, username: response.user.username })
    console.log(`Logged in as ${response.user.displayName}`)
  })

program
  .command('me')
  .description('Show current user')
  .action(async () => {
    printJson(await request<UserProfile>('get', '/users/me'))
  })

program
  .command('dashboard')
  .description('Show dashboard summary')
  .action(async () => {
    const summary = await request<DashboardSummary>('get', '/dashboard/summary')
    printJson(summary)
  })

const moduleCommand = program.command('module').description('Module commands')

moduleCommand
  .command('list')
  .description('List modules')
  .option('-t, --type <type>', 'feature or domain')
  .action(async (options: { type?: string }) => {
    const path = options.type ? `/modules/${options.type === 'domain' ? 'domains' : 'features'}` : '/modules'
    const items = await request<ModuleItem[]>('get', path)
    printItems(
      items,
      'No modules.',
      (item) => `${item.code} [${item.type}] ${item.name} - ${item.description}`,
    )
  })

const tag = program.command('tag').description('Tag commands')

tag
  .command('list')
  .description('List tags')
  .action(async () => {
    const items = await request<TagItem[]>('get', '/tags')
    printItems(items, 'No tags.', (item) => `${item.id} ${item.name} ${item.color} - ${item.description}`)
  })

tag
  .command('add')
  .description('Add a tag')
  .requiredOption('-n, --name <name>', 'tag name')
  .option('-c, --color <color>', 'tag color', '#1d4ed8')
  .option('-d, --description <description>', 'tag description', '')
  .action(async (options: { name: string; color: string; description: string }) => {
    const item = await request<TagItem>('post', '/tags', {
      name: options.name,
      color: options.color,
      description: options.description,
    })
    console.log(`Created tag #${item.id}: ${item.name}`)
  })

tag
  .command('update')
  .description('Update a tag')
  .argument('<id>', 'tag id')
  .requiredOption('-n, --name <name>', 'tag name')
  .option('-c, --color <color>', 'tag color', '#1d4ed8')
  .option('-d, --description <description>', 'tag description', '')
  .action(async (id: string, options: { name: string; color: string; description: string }) => {
    const item = await request<TagItem>('put', `/tags/${id}`, {
      name: options.name,
      color: options.color,
      description: options.description,
    })
    console.log(`Updated tag #${item.id}: ${item.name}`)
  })

tag
  .command('delete')
  .description('Delete a tag')
  .argument('<id>', 'tag id')
  .action(async (id: string) => {
    await request<void>('delete', `/tags/${id}`)
    console.log(`Deleted tag #${id}`)
  })

const knowledge = program.command('knowledge').description('Knowledge commands')

knowledge
  .command('tree')
  .description('Show Markdown knowledge tree')
  .option('--json', 'print the full response as JSON')
  .action(async (options: { json?: boolean }) => {
    const nodes = await request<KnowledgeNode[]>('get', '/knowledge/tree')
    if (options.json) {
      printJson(nodes)
      return
    }
    if (nodes.length === 0) {
      console.log('No knowledge files.')
      return
    }
    for (const line of formatKnowledgeTree(nodes)) {
      console.log(line)
    }
  })

knowledge
  .command('stats')
  .description('Show Markdown knowledge statistics')
  .action(async () => {
    printJson(await request<KnowledgeStats>('get', '/knowledge/stats'))
  })

knowledge
  .command('search')
  .description('Search Markdown knowledge files')
  .argument('<query>', 'search query')
  .action(async (query: string) => {
    const items = await request<KnowledgeSearchResult[]>('get', '/knowledge/search', undefined, { q: query })
    printItems(items, 'No knowledge results.', (item) => `${item.path} (${item.score})\n  ${item.snippet}`)
  })

knowledge
  .command('read')
  .description('Read a Markdown knowledge file')
  .argument('<path>', 'knowledge file path, such as README.md')
  .option('--json', 'print the full response as JSON')
  .action(async (path: string, options: { json?: boolean }) => {
    const file = await request<KnowledgeFile>('get', '/knowledge/files', undefined, { path })
    if (options.json) {
      printJson(file)
      return
    }
    console.log(`# ${file.path}`)
    console.log('')
    console.log(file.content)
  })

const record = program.command('record').description('Record commands')

record
  .command('list')
  .description('List records')
  .option('-m, --module <moduleCode>', 'filter by module code')
  .option('--tag-id <tagId>', 'filter by tag id')
  .option('-d, --date <date>', 'filter by record date YYYY-MM-DD')
  .option('-q, --keyword <keyword>', 'search title or content')
  .action(async (options: { module?: string; tagId?: string; date?: string; keyword?: string }) => {
    const items = await request<RecordItem[]>('get', '/records', undefined, {
      moduleCode: options.module,
      tagId: options.tagId ? Number(options.tagId) : undefined,
      recordDate: options.date,
      keyword: options.keyword,
    })
    printItems(items, 'No records.', (item) => {
      const tags = item.tags.length > 0 ? ` #${item.tags.map((tag) => tag.name).join(',#')}` : ''
      return `${item.id} [${item.moduleCode}] ${item.recordDate} ${item.title}${tags}`
    })
  })

record
  .command('add')
  .description('Add a record')
  .requiredOption('-t, --title <title>', 'record title')
  .option('-m, --module <moduleCode>', 'module code', 'life')
  .option('-c, --content <content>', 'record content', '')
  .option('-d, --date <date>', 'record date YYYY-MM-DD')
  .option('--tag-ids <ids>', 'comma-separated tag ids')
  .action(async (options: { title: string; module: string; content: string; date?: string; tagIds?: string }) => {
    const item = await request<RecordItem>('post', '/records', {
      moduleCode: options.module,
      title: options.title,
      content: options.content,
      recordDate: options.date,
      tagIds: parseIds(options.tagIds),
    })
    console.log(`Created record #${item.id}: ${item.title}`)
  })

record
  .command('update')
  .description('Update a record')
  .argument('<id>', 'record id')
  .requiredOption('-t, --title <title>', 'record title')
  .option('-m, --module <moduleCode>', 'module code', 'life')
  .option('-c, --content <content>', 'record content', '')
  .option('-d, --date <date>', 'record date YYYY-MM-DD')
  .option('--tag-ids <ids>', 'comma-separated tag ids')
  .action(async (id: string, options: { title: string; module: string; content: string; date?: string; tagIds?: string }) => {
    const item = await request<RecordItem>('put', `/records/${id}`, {
      moduleCode: options.module,
      title: options.title,
      content: options.content,
      recordDate: options.date,
      tagIds: parseIds(options.tagIds),
    })
    console.log(`Updated record #${item.id}: ${item.title}`)
  })

record
  .command('delete')
  .description('Delete a record')
  .argument('<id>', 'record id')
  .action(async (id: string) => {
    await request<void>('delete', `/records/${id}`)
    console.log(`Deleted record #${id}`)
  })

const task = program.command('task').description('Task commands')

task
  .command('summary')
  .description('Show task summary')
  .action(async () => {
    printJson(await request<TaskSummary>('get', '/tasks/summary'))
  })

task
  .command('list')
  .description('List tasks')
  .option('-s, --status <status>', 'filter by status')
  .option('-m, --module <moduleCode>', 'filter by module code')
  .option('-p, --priority <priority>', 'filter by priority')
  .option('--due <date>', 'filter by due date YYYY-MM-DD')
  .action(async (options: { status?: string; module?: string; priority?: string; due?: string }) => {
    const items = await request<TaskItem[]>('get', '/tasks', undefined, {
      status: options.status,
      moduleCode: options.module,
      priority: options.priority,
      dueDate: options.due,
    })
    printItems(items, 'No tasks.', (item) => `${item.id} [${item.status}] ${item.title} (${item.moduleCode})`)
  })

task
  .command('add')
  .description('Add a task')
  .requiredOption('-t, --title <title>', 'task title')
  .option('-m, --module <moduleCode>', 'module code', 'life')
  .option('-d, --description <description>', 'task description', '')
  .option('-p, --priority <priority>', 'priority', 'medium')
  .option('--due <date>', 'due date YYYY-MM-DD')
  .action(async (options: { title: string; module: string; description: string; priority: string; due?: string }) => {
    const item = await request<TaskItem>('post', '/tasks', {
      moduleCode: options.module,
      title: options.title,
      description: options.description,
      priority: options.priority,
      dueDate: options.due,
    })
    console.log(`Created task #${item.id}: ${item.title}`)
  })

task
  .command('update')
  .description('Update a task')
  .argument('<id>', 'task id')
  .requiredOption('-t, --title <title>', 'task title')
  .option('-m, --module <moduleCode>', 'module code', 'life')
  .option('-d, --description <description>', 'task description', '')
  .option('-p, --priority <priority>', 'priority', 'medium')
  .option('--due <date>', 'due date YYYY-MM-DD')
  .action(async (id: string, options: { title: string; module: string; description: string; priority: string; due?: string }) => {
    const item = await request<TaskItem>('put', `/tasks/${id}`, {
      moduleCode: options.module,
      title: options.title,
      description: options.description,
      priority: options.priority,
      dueDate: options.due,
    })
    console.log(`Updated task #${item.id}: ${item.title}`)
  })

task
  .command('done')
  .description('Mark a task as done')
  .argument('<id>', 'task id')
  .action(async (id: string) => {
    const item = await request<TaskItem>('patch', `/tasks/${id}/status`, undefined, { status: 'done' })
    console.log(`Task #${item.id} is ${item.status}`)
  })

task
  .command('status')
  .description('Update task status')
  .argument('<id>', 'task id')
  .argument('<status>', 'todo, in_progress, done, or canceled')
  .action(async (id: string, status: string) => {
    const item = await request<TaskItem>('patch', `/tasks/${id}/status`, undefined, { status })
    console.log(`Task #${item.id} is ${item.status}`)
  })

task
  .command('delete')
  .description('Delete a task')
  .argument('<id>', 'task id')
  .action(async (id: string) => {
    await request<void>('delete', `/tasks/${id}`)
    console.log(`Deleted task #${id}`)
  })

const finance = program.command('finance').description('Finance commands')

finance
  .command('list')
  .description('List finance transactions')
  .option('--month <month>', 'month YYYY-MM')
  .option('-t, --type <type>', 'income or expense')
  .option('-c, --category <category>', 'category')
  .action(async (options: { month?: string; type?: string; category?: string }) => {
    const items = await request<FinanceTransactionItem[]>('get', '/finance/transactions', undefined, {
      month: options.month,
      type: options.type,
      category: options.category,
    })
    printItems(
      items,
      'No finance transactions.',
      (item) => `${item.id} [${item.type}] ${item.amount} ${item.category} ${item.transactionDate}`,
    )
  })

finance
  .command('add')
  .description('Add a finance transaction')
  .requiredOption('-a, --amount <amount>', 'amount')
  .requiredOption('-c, --category <category>', 'category')
  .option('-t, --type <type>', 'income or expense', 'expense')
  .option('--account <account>', 'account', 'default')
  .option('--merchant <merchant>', 'merchant', '')
  .option('-n, --note <note>', 'note', '')
  .option('-d, --date <date>', 'transaction date YYYY-MM-DD')
  .action(async (options: {
    amount: string
    category: string
    type: string
    account: string
    merchant: string
    note: string
    date?: string
  }) => {
    const item = await request<FinanceTransactionItem>('post', '/finance/transactions', {
      type: options.type,
      amount: options.amount,
      category: options.category,
      account: options.account,
      merchant: options.merchant,
      note: options.note,
      transactionDate: options.date,
    })
    console.log(`Created transaction #${item.id}: ${item.type} ${item.amount}`)
  })

finance
  .command('update')
  .description('Update a finance transaction')
  .argument('<id>', 'transaction id')
  .requiredOption('-a, --amount <amount>', 'amount')
  .requiredOption('-c, --category <category>', 'category')
  .option('-t, --type <type>', 'income or expense', 'expense')
  .option('--account <account>', 'account', 'default')
  .option('--merchant <merchant>', 'merchant', '')
  .option('-n, --note <note>', 'note', '')
  .option('-d, --date <date>', 'transaction date YYYY-MM-DD')
  .action(async (id: string, options: {
    amount: string
    category: string
    type: string
    account: string
    merchant: string
    note: string
    date?: string
  }) => {
    const item = await request<FinanceTransactionItem>('put', `/finance/transactions/${id}`, {
      type: options.type,
      amount: options.amount,
      category: options.category,
      account: options.account,
      merchant: options.merchant,
      note: options.note,
      transactionDate: options.date,
    })
    console.log(`Updated transaction #${item.id}: ${item.type} ${item.amount}`)
  })

finance
  .command('delete')
  .description('Delete a finance transaction')
  .argument('<id>', 'transaction id')
  .action(async (id: string) => {
    await request<void>('delete', `/finance/transactions/${id}`)
    console.log(`Deleted transaction #${id}`)
  })

finance
  .command('summary')
  .description('Show monthly finance summary')
  .option('--month <month>', 'month YYYY-MM')
  .action(async (options: { month?: string }) => {
    printJson(await request<FinanceMonthlySummary>('get', '/finance/summary/monthly', undefined, { month: options.month }))
  })

finance
  .command('categories')
  .description('Show monthly expense summary by category')
  .option('--month <month>', 'month YYYY-MM')
  .action(async (options: { month?: string }) => {
    const items = await request<FinanceCategorySummary[]>('get', '/finance/summary/monthly/categories', undefined, {
      month: options.month,
    })
    printItems(
      items,
      'No category summary.',
      (item) => `${item.category}: ${item.amount} (${(Number(item.ratio) * 100).toFixed(1)}%)`,
    )
  })

finance
  .command('accounts')
  .description('Show monthly finance summary by account')
  .option('--month <month>', 'month YYYY-MM')
  .action(async (options: { month?: string }) => {
    const items = await request<FinanceAccountSummary[]>('get', '/finance/summary/monthly/accounts', undefined, {
      month: options.month,
    })
    printItems(
      items,
      'No account summary.',
      (item) => `${item.account}: balance ${item.balance}, income ${item.income}, expense ${item.expense}`,
    )
  })

const financeAccount = finance.command('account').description('Finance account commands')

financeAccount
  .command('list')
  .description('List finance accounts')
  .action(async () => {
    const items = await request<FinanceAccountItem[]>('get', '/finance/accounts')
    printItems(
      items,
      'No finance accounts.',
      (item) => `${item.id} ${item.name} [${item.type}] ${item.currency} opening ${item.openingBalance} - ${item.note}`,
    )
  })

financeAccount
  .command('add')
  .description('Add a finance account')
  .requiredOption('-n, --name <name>', 'account name')
  .option('-t, --type <type>', 'account type', 'cash')
  .option('--currency <currency>', 'currency code', 'CNY')
  .option('--opening <amount>', 'opening balance', '0')
  .option('--note <note>', 'note', '')
  .action(async (options: { name: string; type: string; currency: string; opening: string; note: string }) => {
    const item = await request<FinanceAccountItem>('post', '/finance/accounts', {
      name: options.name,
      type: options.type,
      currency: options.currency,
      openingBalance: Number(options.opening),
      note: options.note,
    })
    console.log(`Created finance account #${item.id}: ${item.name}`)
  })

financeAccount
  .command('update')
  .description('Update a finance account')
  .argument('<id>', 'account id')
  .requiredOption('-n, --name <name>', 'account name')
  .option('-t, --type <type>', 'account type', 'cash')
  .option('--currency <currency>', 'currency code', 'CNY')
  .option('--opening <amount>', 'opening balance', '0')
  .option('--note <note>', 'note', '')
  .action(async (id: string, options: { name: string; type: string; currency: string; opening: string; note: string }) => {
    const item = await request<FinanceAccountItem>('put', `/finance/accounts/${id}`, {
      name: options.name,
      type: options.type,
      currency: options.currency,
      openingBalance: Number(options.opening),
      note: options.note,
    })
    console.log(`Updated finance account #${item.id}: ${item.name}`)
  })

financeAccount
  .command('delete')
  .description('Delete a finance account')
  .argument('<id>', 'account id')
  .action(async (id: string) => {
    await request<void>('delete', `/finance/accounts/${id}`)
    console.log(`Deleted finance account #${id}`)
  })

const financeCategory = finance.command('category').description('Finance category commands')

financeCategory
  .command('list')
  .description('List finance categories')
  .option('-t, --type <type>', 'income or expense')
  .action(async (options: { type?: string }) => {
    const items = await request<FinanceCategoryItem[]>('get', '/finance/categories', undefined, { type: options.type })
    printItems(
      items,
      'No finance categories.',
      (item) => `${item.id} [${item.type}] ${item.name} ${item.color} - ${item.note}`,
    )
  })

financeCategory
  .command('add')
  .description('Add a finance category')
  .requiredOption('-n, --name <name>', 'category name')
  .option('-t, --type <type>', 'income or expense', 'expense')
  .option('-c, --color <color>', 'category color', '#2563eb')
  .option('--note <note>', 'note', '')
  .action(async (options: { name: string; type: string; color: string; note: string }) => {
    const item = await request<FinanceCategoryItem>('post', '/finance/categories', {
      name: options.name,
      type: options.type,
      color: options.color,
      note: options.note,
    })
    console.log(`Created finance category #${item.id}: ${item.name}`)
  })

financeCategory
  .command('update')
  .description('Update a finance category')
  .argument('<id>', 'category id')
  .requiredOption('-n, --name <name>', 'category name')
  .option('-t, --type <type>', 'income or expense', 'expense')
  .option('-c, --color <color>', 'category color', '#2563eb')
  .option('--note <note>', 'note', '')
  .action(async (id: string, options: { name: string; type: string; color: string; note: string }) => {
    const item = await request<FinanceCategoryItem>('put', `/finance/categories/${id}`, {
      name: options.name,
      type: options.type,
      color: options.color,
      note: options.note,
    })
    console.log(`Updated finance category #${item.id}: ${item.name}`)
  })

financeCategory
  .command('delete')
  .description('Delete a finance category')
  .argument('<id>', 'category id')
  .action(async (id: string) => {
    await request<void>('delete', `/finance/categories/${id}`)
    console.log(`Deleted finance category #${id}`)
  })

const review = program.command('review').description('Review commands')

review
  .command('list')
  .description('List reviews')
  .option('--type <reviewType>', 'filter by review type')
  .option('-m, --module <moduleCode>', 'filter by module code')
  .option('--start <date>', 'filter by period start YYYY-MM-DD')
  .option('--end <date>', 'filter by period end YYYY-MM-DD')
  .action(async (options: { type?: string; module?: string; start?: string; end?: string }) => {
    const items = await request<ReviewItem[]>('get', '/reviews', undefined, {
      reviewType: options.type,
      moduleCode: options.module,
      periodStart: options.start,
      periodEnd: options.end,
    })
    printItems(items, 'No reviews.', (item) => `${item.id} [${item.reviewType}] ${item.title} ${item.periodStart}..${item.periodEnd}`)
  })

review
  .command('add')
  .description('Add a review')
  .requiredOption('-t, --title <title>', 'review title')
  .option('--type <reviewType>', 'weekly, monthly, or module', 'weekly')
  .option('-m, --module <moduleCode>', 'module code', 'life')
  .option('-s, --summary <summary>', 'summary', '')
  .option('--highlights <highlights>', 'highlights', '')
  .option('--problems <problems>', 'problems', '')
  .option('--next <nextActions>', 'next actions', '')
  .option('--start <date>', 'period start YYYY-MM-DD')
  .option('--end <date>', 'period end YYYY-MM-DD')
  .action(async (options: {
    title: string
    type: string
    module: string
    summary: string
    highlights: string
    problems: string
    next: string
    start?: string
    end?: string
  }) => {
    const item = await request<ReviewItem>('post', '/reviews', {
      reviewType: options.type,
      moduleCode: options.module,
      title: options.title,
      summary: options.summary,
      highlights: options.highlights,
      problems: options.problems,
      nextActions: options.next,
      periodStart: options.start,
      periodEnd: options.end,
    })
    console.log(`Created review #${item.id}: ${item.title}`)
  })

review
  .command('update')
  .description('Update a review')
  .argument('<id>', 'review id')
  .requiredOption('-t, --title <title>', 'review title')
  .option('--type <reviewType>', 'weekly, monthly, or module', 'weekly')
  .option('-m, --module <moduleCode>', 'module code', 'life')
  .option('-s, --summary <summary>', 'summary', '')
  .option('--highlights <highlights>', 'highlights', '')
  .option('--problems <problems>', 'problems', '')
  .option('--next <nextActions>', 'next actions', '')
  .option('--start <date>', 'period start YYYY-MM-DD')
  .option('--end <date>', 'period end YYYY-MM-DD')
  .action(async (id: string, options: {
    title: string
    type: string
    module: string
    summary: string
    highlights: string
    problems: string
    next: string
    start?: string
    end?: string
  }) => {
    const item = await request<ReviewItem>('put', `/reviews/${id}`, {
      reviewType: options.type,
      moduleCode: options.module,
      title: options.title,
      summary: options.summary,
      highlights: options.highlights,
      problems: options.problems,
      nextActions: options.next,
      periodStart: options.start,
      periodEnd: options.end,
    })
    console.log(`Updated review #${item.id}: ${item.title}`)
  })

review
  .command('delete')
  .description('Delete a review')
  .argument('<id>', 'review id')
  .action(async (id: string) => {
    await request<void>('delete', `/reviews/${id}`)
    console.log(`Deleted review #${id}`)
  })

program.parseAsync(process.argv).catch((error: unknown) => {
  const message = error instanceof Error ? error.message : String(error)
  console.error(message)
  process.exitCode = 1
})

function parseIds(value?: string) {
  if (!value) {
    return []
  }
  return value.split(',')
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isFinite(item))
}

function formatKnowledgeTree(nodes: KnowledgeNode[], depth = 0): string[] {
  const lines: string[] = []
  for (const node of nodes) {
    const prefix = '  '.repeat(depth)
    const marker = node.type === 'directory' ? '/' : '-'
    lines.push(`${prefix}${marker} ${node.path || node.name}`)
    lines.push(...formatKnowledgeTree(node.children, depth + 1))
  }
  return lines
}
