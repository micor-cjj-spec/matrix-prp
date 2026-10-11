import { apiClient, type ApiResponse } from './client'
export type Kind = 'single' | 'multiple' | 'boolean'
export interface Subject { id:number; parentId:number|null; name:string; description:string }
export interface SubjectForm { parentId:number|null; name:string; description:string }
export interface Bank { id:number; subjectId:number; title:string; description:string; sourceName:string; licenseNote:string; status:'draft'|'published' }
export type BankForm = Omit<Bank, 'id'|'status'>
export interface Option { key:string; text:string }
export interface QuestionForm { type:Kind; stem:string; options:Option[]; answers:string[]; explanation:string; difficulty:'easy'|'medium'|'hard' }
export interface Question extends QuestionForm { id:number; bankId:number; status:'draft'|'published' }
export interface PlayQuestion { id:number; bankId:number; type:Kind; stem:string; options:Option[]; difficulty:string }
export interface ImportForm { format:'json'|'csv'; content:string; sourceName:string }
export interface ImportResult { imported:number; duplicates:number }
export interface ImportPreview { total:number; examples:QuestionForm[] }
export interface GradeResult { correct:boolean; correctAnswers:string[]; explanation:string }
export interface Statistics { attempted:number; correct:number; wrong:number }

const data = async <T>(p:Promise<{data:ApiResponse<T>}>):Promise<T> => (await p).data.data
export const getSubjects = () => data(apiClient.get<ApiResponse<Subject[]>>('/practice/subjects'))
export const addSubject = (v:SubjectForm) => data(apiClient.post<ApiResponse<Subject>>('/practice/subjects',v))
export const editSubject = (id:number,v:SubjectForm) => apiClient.put('/practice/subjects/'+id,v)
export const removeSubject = (id:number) => apiClient.delete('/practice/subjects/'+id)
export const getBanks = (id:number) => data(apiClient.get<ApiResponse<Bank[]>>('/practice/subjects/'+id+'/banks'))
export const addBank = (v:BankForm) => data(apiClient.post<ApiResponse<Bank>>('/practice/banks',v))
export const editBank = (id:number,v:BankForm) => apiClient.put('/practice/banks/'+id,v)
export const removeBank = (id:number) => apiClient.delete('/practice/banks/'+id)
export const setBankStatus = (id:number,status:'draft'|'published') => apiClient.put('/practice/banks/'+id+'/status',null,{params:{status}})
export const getQuestions = (id:number) => data(apiClient.get<ApiResponse<Question[]>>('/practice/banks/'+id+'/questions'))
export const addQuestion = (id:number,v:QuestionForm) => data(apiClient.post<ApiResponse<Question>>('/practice/banks/'+id+'/questions',v))
export const editQuestion = (id:number,v:QuestionForm) => apiClient.put('/practice/questions/'+id,v)
export const removeQuestion = (id:number) => apiClient.delete('/practice/questions/'+id)
export const setQuestionStatus = (id:number,status:'draft'|'published') => apiClient.put('/practice/questions/'+id+'/status',null,{params:{status}})
export const previewImport = (v:ImportForm) => data(apiClient.post<ApiResponse<ImportPreview>>('/practice/imports/preview',v))
export const importQuestions = (id:number,v:ImportForm) => data(apiClient.post<ApiResponse<ImportResult>>('/practice/banks/'+id+'/imports',v,{timeout:30000}))
export const getPlayQuestions = (id:number) => data(apiClient.get<ApiResponse<PlayQuestion[]>>('/practice/banks/'+id+'/play'))
export const submitAnswer = (id:number,answers:string[]) => data(apiClient.post<ApiResponse<GradeResult>>('/practice/questions/'+id+'/check',{answers}))
export const getStatistics = () => data(apiClient.get<ApiResponse<Statistics>>('/practice/statistics'))
export const getWrongQuestions = () => data(apiClient.get<ApiResponse<PlayQuestion[]>>('/practice/wrong-questions'))
export const generateQuestions = (id:number,topic:string,difficulty:string,count:number) => data(apiClient.post<ApiResponse<ImportResult>>('/practice/banks/'+id+'/ai/generate',{topic,difficulty,count},{timeout:50000}))
export const explainQuestion = (id:number,question:string) => data(apiClient.post<ApiResponse<{content:string}>>('/practice/questions/'+id+'/ai/explain',{question},{timeout:50000}))
