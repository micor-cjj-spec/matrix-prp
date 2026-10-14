/**
 * Intent for an editable meal card. The frontend only routes requests;
 * the backend owns conversation lookup, draft creation and authorization.
 */
export function isMealCardRequest(text: string, hasRecentMeal: boolean): boolean {
  const content = text.trim().replace(/^@健康\s*/u, '')
  if (!content || content.length > 180) return false
  // "Design a card UI" is an engineering request, never a health write.
  if (/(?:如何|怎么|为什么|代码|接口|组件|页面|需求|设计|开发|实现|测试|报错|修复)/u.test(content)) return false
  if (/(?:日志|会议|笔记|任务|备忘)/u.test(content)) return false
  const action = /(?:创建|生成|制作|做|出|整理|准备|弄|填写|录入|录人|导入|写入|归档|记录|保存|记一下)/u.test(content)
  const card = /(?:卡片|草稿|健康记录|饮食记录|餐食记录)/u.test(content)
  // Card-less references ("帮我录入一下") must remain supported when
  // the selected conversation already contains a real user meal.
  const shortFollowup = hasRecentMeal &&
    /(?:帮我|给我|请|麻烦).{0,18}(?:录入|录人|导入|写入|归档|记录|保存|记一下)/u.test(content)
  if (!action || (!card && !shortFollowup)) return false
  const meal = /(?:早餐|早饭|午餐|午饭|晚餐|晚饭|今晚|早上|中午|晚上|加餐|夜宵|吃的|吃了|这顿|这餐|热量|食物|饮食|健康)/u.test(content)
  return meal || hasRecentMeal
}
