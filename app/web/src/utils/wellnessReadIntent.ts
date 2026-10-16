/**
 * Only selects an authorisation preview; never reads personal data by itself.
 * Meal writing continues through the existing explicitly confirmed draft flow.
 */
export function isWellnessReadQuery(message: string): boolean {
  const text = message.trim()
  if (!text || /(?:如何开发|怎么开发|如何设计|怎么实现|报错原因|错误日志)/u.test(text)) return false
  if (!/(?:早餐|早饭|午餐|午饭|晚餐|晚饭|用餐|饮食|餐次|三餐|餐食|吃饭|饭菜|每顿)/u.test(text)) return false
  if (/(?:帮我补录|请补录|现在录入|帮我记下|帮我新增|帮我添加|直接保存|帮我记录)/u.test(text)
      && !/(?:查|查询|哪些|哪几|有没有|是否)/u.test(text)) return false
  return /(?:查询|查一下|查查|帮我查|查出|查看|检查|核对|统计|列出|有哪些|哪几|哪些|漏录|漏记|没录|没有录|未录|没记|没有记|缺记录|是否录入|有没有录)/u.test(text)
}
