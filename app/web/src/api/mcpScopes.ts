export const mcpScopes = [
  { value: 'prp.tasks.read', label: '读取任务' },
  { value: 'prp.finance.read', label: '读取财务' },
  { value: 'prp.wellness.read', label: '读取健康记录' },
  { value: 'prp.write.create', label: '生成待确认草稿' },
  { value: 'prp.write.update', label: '生成任务修改草稿' },
  { value: 'prp.write.delete', label: '生成任务删除草稿' },
  { value: 'prp.write.status', label: '查看草稿状态' },
  { value: 'prp.write.confirm', label: '提交已在 PRP 审批的草稿' },
] as const
