/** 展示层中文映射；保留后端传输和持久化的英文枚举值。 */
const modules: Record<string,string> = {records:'记录管理',tasks:'任务计划',finance:'财务',reviews:'复盘中心',knowledge:'知识库',life:'生活',learning:'学习',work:'工作',interests:'兴趣',social:'社交'}
const statuses: Record<string,string> = {todo:'待办',in_progress:'进行中',done:'已完成',canceled:'已取消'}
const priorities: Record<string,string> = {low:'低',medium:'中',high:'高'}
const financeTypes: Record<string,string> = {expense:'支出',income:'收入'}
const accountTypes: Record<string,string> = {cash:'现金',bank:'银行账户',card:'银行卡'}
const reviewTypes: Record<string,string> = {weekly:'每周复盘',monthly:'每月复盘',module:'专题复盘'}
const notificationCategories: Record<string,string> = {CUSTOM:'自定义',STUDY:'学习',WORK:'工作',LIFE:'生活',FINANCE:'财务'}
const permissions: Record<string,string> = {granted:'已允许',denied:'已拒绝',default:'尚未授权',unsupported:'不支持'}
export const moduleLabel = (key:string) => modules[key] ?? key
export const taskStatusLabel = (key:string) => statuses[key] ?? key
export const priorityLabel = (key:string) => priorities[key] ?? key
export const financeTypeLabel = (key:string) => financeTypes[key] ?? key
export const accountTypeLabel = (key:string) => accountTypes[key] ?? key
export const reviewTypeLabel = (key:string) => reviewTypes[key] ?? key
export const notificationCategoryLabel = (key:string) => notificationCategories[key] ?? key
export const notificationPermissionLabel = (key:string) => permissions[key] ?? key
