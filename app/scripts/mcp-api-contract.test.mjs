import test from 'node:test'
import assert from 'node:assert/strict'
import {audit, parseControllerRoutes, toMarkdown} from './mcp-api-contract.mjs'

const registry = {
  tools: new Set(['prp_tasks_list', 'prp_prepare_task', 'prp_example_get']),
  scopes: new Map([
    ['prp_tasks_list', 'prp.tasks.read'],
    ['prp_prepare_task', 'prp.write.create'],
    ['prp_example_get', 'prp.example.read']
  ]),
  oauth: '"prp.tasks.read" "prp.write.create" "prp.example.read"'
}
const legacy = {controllers: {'tasks/api/TaskController.java': ['GET /api/tasks']}}
const routes = [{route: 'GET /api/tasks', controller: 'tasks/api/TaskController.java'}]
const catalog = {routes: [{route: 'GET /api/tasks', status: 'mapped', tool: 'prp_tasks_list'}]}

test('extract Spring REST routes with class prefix, no-argument mapping and named values', () => {
  const java = [
    '@RestController',
    '@RequestMapping("/api/tasks")',
    'public class TaskController {',
    '  @GetMapping public Object list() {return null;}',
    '  @PostMapping(value = "/{id}/confirm", consumes = "application/json")',
    '  public Object confirm() {return null;}',
    '  @RequestMapping(path="/archive", method=RequestMethod.PATCH)',
    '  public Object archive() {return null;}',
    '}'
  ].join('\n')
  const got = parseControllerRoutes(java, 'TaskController.java').map(x => x.route)
  assert.deepEqual(got, [
    'GET /api/tasks', 'POST /api/tasks/{id}/confirm', 'PATCH /api/tasks/archive'
  ])
})

test('scan direct full paths and ignore non REST controllers', () => {
  const java = '@RestController public class Note { @GetMapping("/api/notes") public Object list(){return null;} }'
  assert.deepEqual(parseControllerRoutes(java, 'Note.java').map(x => x.route), ['GET /api/notes'])
  assert.deepEqual(parseControllerRoutes(java.replace('@RestController', '@Controller'), 'Note.java'), [])
})

test('baseline routes with valid tool are counted as mapped', () => {
  const result = audit(routes, legacy, catalog, registry)
  assert.equal(result.errors.length, 0)
  assert.equal(result.total, 1)
  assert.equal(result.counts.mapped, 1)
  assert.match(toMarkdown(result), /Mapped/)
})

test('legacy gaps are visible but do not block additions', () => {
  const result = audit(routes, legacy, {routes: []}, registry)
  assert.deepEqual(result.errors, [])
  assert.equal(result.counts['legacy-gap'], 1)
})

test('a brand-new REST route with no MCP decision blocks CI', () => {
  const result = audit([...routes, {route: 'GET /api/tasks/new', controller: 'TaskController.java'}],
    legacy, catalog, registry)
  assert.ok(result.errors.some(x => x.includes('New REST route lacks MCP decision: GET /api/tasks/new')))
})

test('a new REST route cannot claim partial coverage', () => {
  const result = audit([...routes, {route: 'GET /api/tasks/new', controller: 'TaskController.java'}], legacy,
    {routes: [...catalog.routes, {route: 'GET /api/tasks/new', status: 'partial', tool: 'prp_tasks_list',
      reason: 'Only the first ten tasks are available'}]}, registry)
  assert.ok(result.errors.some(x => x.includes('cannot ship with partial MCP coverage')))
})

test('new MCP mapping must be allowlisted and have a real tool-call test', () => {
  const newly = [...routes, {route: 'GET /api/tasks/new', controller: 'TaskController.java'}]
  const status = {routes: [...catalog.routes, {route: 'GET /api/tasks/new',
    status: 'mapped', tool: 'prp_example_get'}]}
  assert.ok(audit(newly, legacy, status, registry).errors.some(x => x.includes('needs tool-call tests')))
  status.routes[1].tests = ['app/backend/src/test/java/com/matrix/prp/mcp/ExampleTests.java']
  assert.ok(audit(newly, legacy, status, registry, () => 'no test reference').errors.some(x => x.includes('Missing MCP tool-call test')))
  assert.deepEqual(audit(newly, legacy, status, registry, () => 'prp_example_get').errors, [])
})

test('new route may be excluded only with a meaningful justification', () => {
  const newly = [...routes, {route: 'POST /api/private/upload', controller: 'PrivateController.java'}]
  const item = {route: 'POST /api/private/upload', status: 'excluded', reason: 'internal'}
  const contract = {routes: [...catalog.routes, item]}
  assert.ok(audit(newly, legacy, contract, registry).errors.some(x => x.includes('meaningful reason')))
  item.reason = 'Raw private file upload is browser-only and never exposed as a model tool'
  assert.deepEqual(audit(newly, legacy, contract, registry).errors, [])
})

test('unknown tools, stale baselines and stale contracts fail', () => {
  const bad = {routes: [{route: 'GET /api/tasks', status: 'mapped', tool: 'prp_not_registered'}]}
  assert.ok(audit(routes, legacy, bad, registry).errors.some(x => x.includes('Unknown MCP tool')))
  const gone = audit([], legacy, catalog, registry)
  assert.ok(gone.errors.some(x => x.includes('Stale frozen route')))
  assert.ok(gone.errors.some(x => x.includes('Mapping for missing REST route')))
})

test('duplicate API routes and duplicate contract entries cannot silently pass', () => {
  const double = audit([...routes, ...routes], legacy,
    {routes: [...catalog.routes, ...catalog.routes]}, registry)
  assert.ok(double.errors.some(x => x.includes('Duplicate REST route')))
  assert.ok(double.errors.some(x => x.includes('Duplicate MCP mapping')))
})
