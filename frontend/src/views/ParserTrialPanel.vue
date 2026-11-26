<template>
  <section class="trial-panel" data-testid="parser-trial-panel">
    <header class="trial-head">
      <div>
        <h3>模板试跑对照（复核视图）</h3>
        <p class="trial-desc">
          选择页面样本与两个模板版本发起试跑：两版共用同一份原文快照，逐字段保留版本标识与来源；
          试跑只写对照与审计数据，不改动线上样本的解析状态与价格。
        </p>
      </div>
    </header>

    <form class="trial-form" @submit.prevent="submitTrial">
      <label>
        <span>站点</span>
        <select v-model="site" data-testid="trial-site">
          <option v-for="item in sites" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <label>
        <span>页面样本</span>
        <select v-model.number="sampleId" data-testid="trial-sample">
          <option v-for="item in sampleOptions" :key="item.id" :value="item.id">
            #{{ item.id }} · {{ item.样本批次 }} · rev{{ item.内容版本 ?? 1 }} · {{ item.status }}
          </option>
        </select>
      </label>
      <label>
        <span>模板版本A</span>
        <select v-model.number="templateAId" data-testid="trial-template-a">
          <option v-for="item in versionOptions" :key="item.id" :value="item.id">
            {{ item.模板名称 }}@{{ item.解析版本 }}（{{ item.status }}）
          </option>
        </select>
      </label>
      <label>
        <span>模板版本B</span>
        <select v-model.number="templateBId" data-testid="trial-template-b">
          <option v-for="item in versionOptions" :key="item.id" :value="item.id">
            {{ item.模板名称 }}@{{ item.解析版本 }}（{{ item.status }}）
          </option>
        </select>
      </label>
      <button class="btn primary" data-testid="start-trial" type="submit" :disabled="!canStart || busy">
        发起试跑
      </button>
      <span v-if="formError" class="error-text" data-testid="trial-form-error">{{ formError }}</span>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th>对照单</th>
          <th>样本来源</th>
          <th>绑定内容</th>
          <th>版本A</th>
          <th>版本B</th>
          <th>审阅状态</th>
          <th>复测状态</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in trials" :key="item.id" :data-testid="`trial-row-${item.id}`">
          <td>#{{ item.id }}</td>
          <td>{{ item.样本批次 }}（{{ item.站点名称 }}）</td>
          <td>rev{{ item.内容版本 }}</td>
          <td>{{ item.模板A.模板名称 }}@{{ item.模板A.解析版本 }}</td>
          <td>{{ item.模板B.模板名称 }}@{{ item.模板B.解析版本 }}</td>
          <td>{{ item.审阅状态 }}</td>
          <td>{{ item.复测状态 }}</td>
          <td>
            <button class="link" type="button" :data-testid="`open-trial-${item.id}`" @click="openTrial(item.id)">
              打开对照单
            </button>
          </td>
        </tr>
        <tr v-if="!trials.length">
          <td colspan="8" class="empty-state">暂无试跑对照单，先选择样本与两个模板版本发起试跑</td>
        </tr>
      </tbody>
    </table>

    <div v-if="current" class="modal-backdrop" data-testid="trial-sheet">
      <div class="modal trial-sheet">
        <h3>字段对照单 #{{ current.id }}</h3>
        <p class="trial-source" data-testid="trial-source">
          样本来源：批次 {{ current.样本来源.样本批次 }} · 站点 {{ current.样本来源.站点名称 }} ·
          指纹 {{ current.样本来源.样本指纹 }} · 抓取 {{ current.样本来源.抓取时间 }} · 绑定内容 rev{{ current.内容版本 }}
        </p>
        <p v-if="staleHint" class="trial-stale" data-testid="trial-stale">{{ staleHint }}</p>
        <pre class="trial-raw" data-testid="trial-raw">{{ current.绑定原文 }}</pre>

        <table class="data-table">
          <thead>
            <tr>
              <th>价格字段</th>
              <th>{{ current.模板A.模板名称 }}@{{ current.模板A.解析版本 }}</th>
              <th>{{ current.模板B.模板名称 }}@{{ current.模板B.解析版本 }}</th>
              <th>对照结论</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in current.字段对照" :key="row.字段" :data-testid="`field-${row.字段}`">
              <td>{{ row.字段 }}</td>
              <td :class="{ 'field-missing': row.A值 == null }">
                <strong>{{ row.A值 ?? '缺失' }}</strong>
                <small v-if="row.A来源" class="field-source">{{ row.A来源 }}</small>
              </td>
              <td :class="{ 'field-missing': row.B值 == null }">
                <strong>{{ row.B值 ?? '缺失' }}</strong>
                <small v-if="row.B来源" class="field-source">{{ row.B来源 }}</small>
              </td>
              <td>{{ row.结论 }}</td>
            </tr>
          </tbody>
        </table>
        <p class="trial-missing" data-testid="trial-missing">
          缺失字段：{{ current.模板A.解析版本 }} [{{ current.缺失字段.版本A.join('、') || '无' }}] ·
          {{ current.模板B.解析版本 }} [{{ current.缺失字段.版本B.join('、') || '无' }}]
        </p>

        <p class="trial-status-line">
          <span class="badge" data-testid="trial-review-status">审阅状态：{{ current.审阅状态 }}</span>
          <span class="badge" data-testid="trial-retest-status">复测状态：{{ current.复测状态 }}</span>
          <span v-if="current.样本当前状态" class="badge muted" data-testid="trial-live-state">
            线上样本：{{ current.样本当前状态 }} · 价格 {{ current.样本线上解析价格 || '—' }}（试跑不回写）
          </span>
        </p>
        <p v-if="scheduleMessage" :class="scheduledOk ? 'trial-ok' : 'error-text'" data-testid="schedule-result">
          {{ scheduleMessage }}
          <RouterLink v-if="scheduledOk" to="/parse_audit" data-testid="goto-audit">前往解析质量审计查看</RouterLink>
        </p>

        <div class="page-actions">
          <button
            v-if="current.审阅状态 !== '已审阅'"
            class="btn"
            type="button"
            data-testid="review-trial"
            :disabled="busy"
            @click="submitReview"
          >
            标记已审阅
          </button>
          <button class="btn primary" type="button" data-testid="schedule-retest" :disabled="busy" @click="submitSchedule">
            安排复测
          </button>
          <button class="btn" type="button" data-testid="rerun-trial" :disabled="busy" @click="submitRerun">
            按当前内容重新试跑
          </button>
          <button class="btn ghost" type="button" data-testid="toggle-correct" @click="toggleCorrect">
            模拟采集更正
          </button>
          <button class="btn ghost" type="button" data-testid="close-trial" @click="closeSheet">关闭</button>
        </div>

        <form v-if="correcting" class="trial-correct" data-testid="correct-form" @submit.prevent="submitCorrect">
          <p class="trial-desc">
            采集层更正样本原文（对照单两列保持审阅时快照，不随更正刷新）：
          </p>
          <textarea v-model="correctContent" rows="4" data-testid="correct-content"></textarea>
          <div class="page-actions">
            <button class="btn primary" type="submit" data-testid="submit-correct" :disabled="busy">确认更正</button>
            <span v-if="correctMessage" class="trial-ok" data-testid="correct-result">{{ correctMessage }}</span>
          </div>
        </form>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { listEntries } from '@/api/backend-service'
import {
  correctSample,
  getTrial,
  listTrials,
  reviewTrial,
  rerunTrial,
  scheduleRetest,
  startTrial,
} from '@/api/parser-review'
import type { TrialSheet } from '@/api/parser-review'
import type { EntryRow } from '@/data/types'

const templates = ref<EntryRow[]>([])
const samples = ref<EntryRow[]>([])
const trials = ref<TrialSheet[]>([])
const current = ref<TrialSheet | null>(null)
const site = ref('')
const sampleId = ref(0)
const templateAId = ref(0)
const templateBId = ref(0)
const busy = ref(false)
const formError = ref('')
const scheduleMessage = ref('')
const scheduledOk = ref(false)
const correcting = ref(false)
const correctContent = ref('')
const correctMessage = ref('')

const sites = computed(() => {
  const names = templates.value.map((row) => String(row.适用站点 ?? '')).filter(Boolean)
  return [...new Set(names)]
})

const sampleOptions = computed(() =>
  samples.value.filter((row) => String(row.站点名称 ?? '') === site.value),
)

const versionOptions = computed(() =>
  templates.value.filter((row) => String(row.适用站点 ?? '') === site.value),
)

const canStart = computed(
  () => sampleId.value > 0 && templateAId.value > 0 && templateBId.value > 0,
)

watch(site, () => {
  sampleId.value = Number(sampleOptions.value[0]?.id ?? 0)
  templateAId.value = Number(versionOptions.value[0]?.id ?? 0)
  templateBId.value = Number(versionOptions.value[1]?.id ?? 0)
})

const staleHint = computed(() => {
  const sheet = current.value
  if (!sheet || sheet.样本当前内容版本 == null) return ''
  if (Number(sheet.样本当前内容版本) === Number(sheet.内容版本)) return ''
  return `样本采集内容已更正至 rev${sheet.样本当前内容版本}，本对照单仍绑定 rev${sheet.内容版本} 的原文；两列保持审阅时快照，复测资格以服务端校验为准。`
})

async function reloadTrials() {
  const payload = await listTrials()
  trials.value = payload.items
}

async function refreshCurrent() {
  if (!current.value) return
  current.value = await getTrial(current.value.id)
}

async function submitTrial() {
  busy.value = true
  formError.value = ''
  try {
    const result = await startTrial(sampleId.value, templateAId.value, templateBId.value)
    if (!result.ok || !result.trial) {
      formError.value = result.message
      return
    }
    await reloadTrials()
    await openTrial(result.trial.id)
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '试跑发起失败'
  } finally {
    busy.value = false
  }
}

async function openTrial(trialId: number) {
  scheduleMessage.value = ''
  scheduledOk.value = false
  correcting.value = false
  correctMessage.value = ''
  current.value = await getTrial(trialId)
}

function closeSheet() {
  current.value = null
  correcting.value = false
}

async function submitReview() {
  if (!current.value) return
  busy.value = true
  try {
    const result = await reviewTrial(current.value.id)
    if (result.trial) current.value = { ...current.value, ...result.trial }
    scheduleMessage.value = result.message
    scheduledOk.value = result.ok
    await reloadTrials()
    await refreshCurrent()
  } finally {
    busy.value = false
  }
}

async function submitSchedule() {
  if (!current.value) return
  busy.value = true
  try {
    const result = await scheduleRetest(current.value.id)
    scheduledOk.value = result.scheduled
    scheduleMessage.value = result.message
    if (result.trial) current.value = { ...current.value, ...result.trial }
    await reloadTrials()
    await refreshCurrent()
  } finally {
    busy.value = false
  }
}

async function submitRerun() {
  if (!current.value) return
  busy.value = true
  try {
    const result = await rerunTrial(current.value.id)
    if (result.ok && result.trial) {
      await reloadTrials()
      await openTrial(result.trial.id)
    }
    scheduleMessage.value = result.message
    scheduledOk.value = result.ok
  } finally {
    busy.value = false
  }
}

function toggleCorrect() {
  correcting.value = !correcting.value
  correctMessage.value = ''
  if (correcting.value && current.value) {
    correctContent.value = current.value.绑定原文
  }
}

async function submitCorrect() {
  if (!current.value) return
  busy.value = true
  correctMessage.value = ''
  try {
    const result = await correctSample(current.value.样本ID, correctContent.value, '浏览后人工更正')
    correctMessage.value = result.message
    if (result.ok) {
      const sampleRows = await listEntries('sample_store')
      samples.value = sampleRows.items
      await refreshCurrent()
    }
  } catch (error) {
    correctMessage.value = error instanceof Error ? error.message : '更正失败'
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  const [templateRows, sampleRows] = await Promise.all([
    listEntries('page_parser'),
    listEntries('sample_store'),
  ])
  templates.value = templateRows.items
  samples.value = sampleRows.items
  // 默认选中“既有样本、又有两个以上模板版本”的站点，开箱即可试跑。
  const ready = sites.value.find((name) => {
    const sampleCount = samples.value.filter((row) => String(row.站点名称 ?? '') === name).length
    const versionCount = templates.value.filter((row) => String(row.适用站点 ?? '') === name).length
    return sampleCount > 0 && versionCount >= 2
  })
  site.value = ready ?? sites.value[0] ?? ''
  await reloadTrials()
})
</script>
