import { apiClient, type ApiResponse } from './client'

export interface Food {
  id: number; name: string; preparation: string; calories100g: string
  protein100g: string; carbs100g: string; fat100g: string
  sourceNote: string | null; custom: boolean
}
export interface DishTemplate {
  id: number; merchantName: string; dishName: string; portionLabel: string
  portionCount: number | null; caloriesPerServing: number | string
  sourceType: 'USER_ESTIMATE' | 'AI_ESTIMATE' | 'LABEL' | 'OTHER'; sourceNote: string | null
}
export type DishTemplateInput = Omit<DishTemplate, 'id'>
export interface UsdaCandidate {
  fdcId: number; name: string; calories100g: number; protein100g: number
  carbs100g: number; fat100g: number; source: string
}
export interface FoodInput {
  name: string; preparation: string; calories100g: number; protein100g: number
  carbs100g: number; fat100g: number; sourceNote: string
}
export interface MealItem {
  id: number; foodId: number; foodName: string; grams: string
  calories: string; proteinG: string; carbsG: string; fatG: string; estimate: boolean
}
export interface Meal {
  id: number; mealDate: string; mealType: string; note: string | null; items: MealItem[]
}
/** Optional V30 enrichment. No image or full-order OCR is returned. */
export interface MealAnalysisVersion {
  id: number; versionNumber: number; sourceType: 'TEXT' | 'IMAGE'
  rawExtraction: {
    schemaVersion?: number
    sourceType?: string
    items?: Array<{ name: string; estimatedGrams: number | string | null }>
    sourceContext?: {
      kind: 'FOOD_PHOTO' | 'ORDER_SCREENSHOT' | 'NUTRITION_LABEL'
      merchantName?: string
      lineItems?: Array<{
        name: string
        purchasedQuantity?: number | string
        portionLabel?: string
        packageGrams?: number | string
        labelVerified?: boolean
        labelPer100gCandidate?: {
          caloriesKcal?: number | string
          proteinG?: number | string
          carbsG?: number | string
          fatG?: number | string
          fiberG?: number | string
          sugarG?: number | string
          sodiumMg?: number | string
        }
      }>
    }
  }
  analysis: {
    schemaVersion?: number
    confirmed?: boolean
    method?: string
    items?: Array<{
      foodName: string; weightGrams: number | string | null
      caloriesKcal: number | string | null
      proteinG: number | string | null
      carbsG: number | string | null; fatG: number | string | null
      source: string; unknownWeight?: boolean
    }>
  }
  modelKey: string | null; createdAt: string
}
export interface MealNutrientDetails {
  mealItemId: number; foodName: string
  proteinG: number | string | null; carbsG: number | string | null
  fatG: number | string | null; fiberG: number | string | null
  sugarG: number | string | null; sodiumMg: number | string | null
  sourceType: string; confidenceLevel: string
  estimateNote: string | null; weightMinG: number | string | null
  weightMaxG: number | string | null
  caloriesMinKcal: number | string | null; caloriesMaxKcal: number | string | null
}
export interface MealAnalysisDetails {
  meal: Meal; analyses: MealAnalysisVersion[]
  nutrients: MealNutrientDetails[]
  nutritionCompleteness: {
    foodCount: number; knownProteinCount: number
    knownCarbsCount: number; knownFatCount: number
  }
}
/** Confirmed manually by the owner; model OCR values alone never produce this payload. */
export interface NutritionLabelVerificationInput {
  mealItemId: number; consumedGrams: number
  caloriesPer100g: number; proteinPer100g: number
  carbsPer100g: number; fatPer100g: number
  fiberPer100g: number | null; sugarPer100g: number | null
  sodiumMgPer100g: number | null; userVerified: boolean
}
export interface ItemInput { foodId: number; grams: number }
export interface MealSnapshotItem {
  foodId: number | null; name: string | null; grams: number; calories: number | null
}
export interface MealSnapshotInput {
  mealDate: string; mealType: string; note: string; items: MealSnapshotItem[]
  idempotencyKey?: string
}
export interface MealInput {
  mealDate: string; mealType: string; note: string; items: ItemInput[]; idempotencyKey?: string
}
export interface Exercise {
  id: number; performedOn: string; name: string; durationMinutes: number
  estimatedKcal: string | null; note: string | null
}
export interface ExerciseInput {
  performedOn: string; name: string; durationMinutes: number
  estimatedKcal: number | null; note: string
}
export interface BodyMetric {
  id: number; measuredOn: string; weightKg: string
  bodyFatPct: string | null; waistCm: string | null
}
export interface BodyMetricInput {
  measuredOn: string; weightKg: number; bodyFatPct: number | null; waistCm: number | null
}
export interface Goal {
  id: number; effectiveFrom: string; dailyCalories: string
  dailyProteinG: string | null; weeklyActivityMinutes: number | null
}
export interface GoalInput {
  effectiveFrom: string; dailyCalories: number
  dailyProteinG: number | null; weeklyActivityMinutes: number | null
}
export interface Profile { heightCm: string | null; timezone: string }
export interface DailySummary {
  date: string; calories: string | null; proteinG: string | null; carbsG: string | null
  fatG: string | null; mealCount: number; exerciseMinutes: number
  exerciseEstimatedKcal: string | null; latestWeightKg: string | null
  goal: Goal | null; recordedMealTypes: string[]
}
export interface TrendPoint {
  date: string; calories: string | null; exerciseMinutes: number | null; weightKg: string | null
}
async function get<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const res = await apiClient.get<ApiResponse<T>>(url, { params })
  return res.data.data
}
async function post<T>(url: string, body: unknown): Promise<T> {
  const res = await apiClient.post<ApiResponse<T>>(url, body)
  return res.data.data
}
async function put<T>(url: string, body: unknown): Promise<T> {
  const res = await apiClient.put<ApiResponse<T>>(url, body)
  return res.data.data
}
async function del(url: string): Promise<void> { await apiClient.delete(url) }

export const wellnessApi = {
  dishes: (q = '') => get<DishTemplate[]>('/wellness/dishes', { q }),
  dish: (id: number) => get<DishTemplate>('/wellness/dishes/' + id),
  addDish: (input: DishTemplateInput) => post<DishTemplate>('/wellness/dishes', input),
  updateDish: (id: number, input: DishTemplateInput) => put<DishTemplate>('/wellness/dishes/' + id, input),
  deleteDish: (id: number) => del('/wellness/dishes/' + id),
  foods: (q = '') => get<Food[]>('/wellness/foods', { q }),
  food: (id: number) => get<Food>('/wellness/foods/' + id),
  frequent: () => get<Food[]>('/wellness/foods/frequent'),
  usdaStatus: () => get<{ configured: boolean }>('/wellness/foods/usda/status'),
  searchUsda: (q: string) => get<UsdaCandidate[]>('/wellness/foods/usda/search', { q }),
  importUsda: (fdcId: number, alias?: string) => post<Food>(
    '/wellness/foods/usda/' + fdcId + '/import' + (alias ? '?alias=' + encodeURIComponent(alias) : ''), {}),
  addFood: (form: FoodInput) => post<Food>('/wellness/foods', form),
  meals: (date: string) => get<Meal[]>('/wellness/meals', { date }),
  mealAnalysis: (id: number) => get<MealAnalysisDetails>('/wellness/meals/' + id + '/analysis'),
  verifyMealLabel: (id: number, input: NutritionLabelVerificationInput) =>
    post<MealAnalysisDetails>('/wellness/meals/' + id + '/label-verification', input),
  addMeal: (form: MealInput) => post<Meal>('/wellness/meals', form),
  addMealSnapshots: (form: MealSnapshotInput) => post<Meal>('/wellness/meals/snapshots', form),
  updateMealSnapshots: (id: number, form: MealSnapshotInput) =>
    put<Meal>('/wellness/meals/' + id + '/snapshots', form),
  updateMeal: (id: number, form: MealInput) => put<Meal>('/wellness/meals/' + id, form),
  deleteMeal: (id: number) => del('/wellness/meals/' + id),
  copyMeal: (id: number, date: string) => post<Meal>('/wellness/meals/' + id + '/copy?date=' + encodeURIComponent(date), {}),
  exercises: (date: string) => get<Exercise[]>('/wellness/exercises', { date }),
  addExercise: (form: ExerciseInput) => post<Exercise>('/wellness/exercises', form),
  updateExercise: (id: number, form: ExerciseInput) => put<Exercise>('/wellness/exercises/' + id, form),
  deleteExercise: (id: number) => del('/wellness/exercises/' + id),
  metrics: (days = 30) => get<BodyMetric[]>('/wellness/body-metrics', { days }),
  addMetric: (form: BodyMetricInput) => post<BodyMetric>('/wellness/body-metrics', form),
  updateMetric: (id: number, form: BodyMetricInput) => put<BodyMetric>('/wellness/body-metrics/' + id, form),
  deleteMetric: (id: number) => del('/wellness/body-metrics/' + id),
  goals: () => get<Goal[]>('/wellness/goals'),
  saveGoal: (form: GoalInput) => post<Goal>('/wellness/goals', form),
  profile: () => get<Profile>('/wellness/profile'),
  saveProfile: (form: Profile) => put<Profile>('/wellness/profile', form),
  daily: (date: string) => get<DailySummary>('/wellness/summary/daily', { date }),
  trends: (days = 14) => get<TrendPoint[]>('/wellness/summary/trends', { days }),
}
