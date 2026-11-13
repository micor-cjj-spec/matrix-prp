export const mcpScopes = [
  { value: 'prp.tasks.read', label: '读取任务' },
  { value: 'prp.records.read', label: '读取个人记录摘要' },
  { value: 'prp.practice.read', label: '读取学习题库和练习统计' },
  { value: 'prp.finance.read', label: '读取财务' },
  { value: 'prp.wellness.read', label: '读取健康记录' },
  { value: 'prp.write.create', label: '生成待确认草稿' },
  { value: 'prp.write.update', label: '生成任务修改草稿' },
  { value: 'prp.write.delete', label: '生成任务删除草稿' },
  { value: 'prp.write.status', label: '查看草稿状态' },
  { value: 'prp.write.confirm', label: '提交已在 PRP 审批的草稿' },
  { value: 'prp.wellness.write.create', label: '生成健康新增草稿' },
  { value: 'prp.wellness.write.update', label: '生成健康修改草稿' },
  { value: 'prp.wellness.write.delete', label: '生成健康删除草稿' },
  { value: 'prp.wellness.write.status', label: '查看健康草稿' },
  { value: 'prp.wellness.write.confirm', label: '提交已审批的健康草稿' },
] as const

/** Discovery restricts selectable scopes; it never grants them. Missing/invalid discovery fails closed. */
export function advertisedMcpScopes(value: unknown) {
  if (!Array.isArray(value) || value.length === 0 || value.some(v => typeof v !== "string") || new Set(value).size !== value.length) throw new Error("Invalid scope discovery")
  if (value.some(v => !mcpScopes.some(s => s.value === v))) throw new Error("Unknown scope discovery")
  return mcpScopes.filter(s => value.includes(s.value))
}
export function defaultMcpReadScopes(value: readonly { value: string }[]): string[] {
  return value.some(s => s.value === "prp.tasks.read") ? ["prp.tasks.read"] : value.some(s => s.value === "prp.wellness.read") ? ["prp.wellness.read"] : []
}
