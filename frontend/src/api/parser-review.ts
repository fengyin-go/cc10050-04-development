/** 模板试跑对照接口：对照单、审阅、复测安排、复测记录与样本采集更正。 */
import { request } from './client'

export type TrialVersion = {
  id: number
  模板名称: string
  解析版本: string
  适用站点: string
}

export type TrialFieldRow = {
  字段: string
  A值: string | null
  A来源: string | null
  B值: string | null
  B来源: string | null
  结论: string
}

export type TrialSheet = {
  id: number
  样本ID: number
  样本批次: string
  站点名称: string
  内容版本: number
  模板A: TrialVersion
  模板B: TrialVersion
  字段对照: TrialFieldRow[]
  缺失字段: { 版本A: string[]; 版本B: string[] }
  样本来源: { 样本批次: string; 站点名称: string; 抓取时间: string; 样本指纹: string }
  绑定原文: string
  审阅状态: string
  复测状态: string
  复测ID: number | null
  创建时间: string
  审阅时间: string | null
  样本当前内容版本?: number
  样本当前状态?: string
  样本线上解析价格?: string
}

export type RetestRecord = {
  id: number
  审计时间: string
  解析模板: string
  样本总数: string
  字段命中率: string
  失败原因分布: string
  status: string
  记录类型: string
  对照单ID: number
  样本ID: number
  样本批次: string
  站点名称: string
  内容版本: number
  版本A: string
  版本B: string
  价格字段差异: string
  绑定原文: string
  受理状态: string
  资格说明: string
  复测结论: string
  可用于升级: boolean
}

export type TrialResult = {
  ok: boolean
  message: string
  trial?: TrialSheet
}

export type ScheduleResult = {
  ok: boolean
  scheduled: boolean
  message: string
  trial?: TrialSheet
  retest?: RetestRecord
}

async function parseJson<T>(response: Response): Promise<T> {
  const data = (await response.json()) as T & { detail?: string }
  if (!response.ok) {
    throw new Error(data.detail ?? `接口返回 ${response.status}`)
  }
  return data
}

export async function listTrials(): Promise<{ items: TrialSheet[]; total: number }> {
  return parseJson(await request('/api/parser-review/trials'))
}

export async function startTrial(
  sampleId: number,
  templateAId: number,
  templateBId: number,
): Promise<TrialResult> {
  const response = await request('/api/parser-review/trials', {
    method: 'POST',
    body: JSON.stringify({
      sample_id: sampleId,
      template_a_id: templateAId,
      template_b_id: templateBId,
    }),
  })
  return parseJson(response)
}

export async function getTrial(trialId: number): Promise<TrialSheet> {
  return parseJson(await request(`/api/parser-review/trials/${trialId}`))
}

export async function reviewTrial(trialId: number): Promise<TrialResult> {
  const response = await request(`/api/parser-review/trials/${trialId}/review`, { method: 'POST' })
  return parseJson(response)
}

export async function rerunTrial(trialId: number): Promise<TrialResult> {
  const response = await request(`/api/parser-review/trials/${trialId}/rerun`, { method: 'POST' })
  return parseJson(response)
}

export async function scheduleRetest(trialId: number): Promise<ScheduleResult> {
  const response = await request(`/api/parser-review/trials/${trialId}/schedule`, { method: 'POST' })
  return parseJson(response)
}

export async function listRetests(): Promise<{ items: RetestRecord[]; total: number }> {
  return parseJson(await request('/api/parser-review/retests'))
}

export async function correctSample(
  sampleId: number,
  content: string,
  reason: string,
): Promise<{ ok: boolean; message: string }> {
  const response = await request(`/api/parser-review/samples/${sampleId}/correct`, {
    method: 'POST',
    body: JSON.stringify({ content, reason }),
  })
  return parseJson(response)
}
