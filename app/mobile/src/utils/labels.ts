/** 只转换界面上显示的英文枚举，不改变与后端交换的数据。 */
const modules: Record<string,string> = {records:'记录管理',tasks:'任务计划',finance:'财务',reviews:'复盘中心',knowledge:'知识库',life:'生活',learning:'学习',work:'工作',interests:'兴趣',social:'社交'}
const statuses: Record<string,string> = {todo:'待办',in_progress:'进行中',done:'已完成',canceled:'已取消'}
const priorities: Record<string,string> = {low:'低',medium:'中',high:'高'}
const accountTypes: Record<string,string> = {cash:'现金',bank:'银行账户',card:'银行卡'}
export const moduleLabel = (key:string) => modules[key] ?? key
export const taskStatusLabel = (key:string) => statuses[key] ?? key
export const priorityLabel = (key:string) => priorities[key] ?? key
export const accountTypeLabel = (key:string) => accountTypes[key] ?? key
