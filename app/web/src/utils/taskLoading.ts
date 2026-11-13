/**
 * Tasks are the only required resource. Optional statistics and module metadata
 * may fail independently without hiding an otherwise valid task list.
 */
export async function loadTaskResources<TTasks, TSummary, TModules>(
  requestTasks: () => Promise<TTasks>,
  requestSummary: () => Promise<TSummary>,
  requestModules: () => Promise<TModules>,
): Promise<{
  taskItems: TTasks
  summaryResult: PromiseSettledResult<TSummary>
  moduleResult: PromiseSettledResult<TModules>
}> {
  const [taskResult, summaryResult, moduleResult] = await Promise.allSettled([
    requestTasks(), requestSummary(), requestModules(),
  ])
  if (taskResult.status === 'rejected') throw taskResult.reason
  return { taskItems: taskResult.value, summaryResult, moduleResult }
}
