<template>
  <section class="trial-panel" data-testid="audit-retest-panel">
    <header class="trial-head">
      <div>
        <h3>复测记录（模板试跑）</h3>
        <p class="trial-desc">
          审计服务按已审阅对照单里的关联样本与版本校验资格：受理的复测可用于升级判定，
          样本更正或跨站点的请求会被要求复查。
        </p>
      </div>
      <button class="btn ghost" type="button" data-testid="reload-retests" @click="reload">刷新</button>
    </header>

    <table class="data-table">
      <thead>
        <tr>
          <th>复测</th>
          <th>审计时间</th>
          <th>模板版本对比</th>
          <th>样本</th>
          <th>绑定内容</th>
          <th>受理状态</th>
          <th>复测结论</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in records" :key="item.id" :data-testid="`retest-row-${item.id}`">
          <td>#{{ item.id }}</td>
          <td>{{ item.审计时间.slice(0, 19).replace('T', ' ') }}</td>
          <td>{{ item.版本A }} × {{ item.版本B }}</td>
          <td>{{ item.样本批次 }}（{{ item.站点名称 }}）</td>
          <td>rev{{ item.内容版本 }}</td>
          <td>
            <span class="badge" :class="item.受理状态 === '已受理' ? 'ok' : 'warn'">
              {{ item.受理状态 }}
            </span>
          </td>
          <td>{{ item.复测结论 }}</td>
          <td>
            <button class="link" type="button" :data-testid="`open-retest-${item.id}`" @click="openRecord(item)">
              打开差异视图
            </button>
          </td>
        </tr>
        <tr v-if="!records.length">
          <td colspan="8" class="empty-state">暂无复测记录，可先在页面解析模板模块发起试跑并安排复测</td>
        </tr>
      </tbody>
    </table>

    <div v-if="current" class="modal-backdrop" data-testid="retest-diff-view">
      <div class="modal trial-sheet">
        <h3>复测差异视图 #{{ current.id }}</h3>
        <p class="trial-status-line">
          <span class="badge" :class="current.受理状态 === '已受理' ? 'ok' : 'warn'" data-testid="retest-accept">
            {{ current.受理状态 }}
          </span>
          <span class="badge muted">对照单 #{{ current.对照单ID }}</span>
          <span class="badge muted">{{ current.版本A }} × {{ current.版本B }}</span>
        </p>
        <p class="trial-source" data-testid="retest-eligibility">资格说明：{{ current.资格说明 }}</p>
        <p class="trial-source" data-testid="retest-conclusion">
          复测结论：{{ current.复测结论 }}（{{ current.可用于升级 ? '可用于升级判定' : '不可用于升级判定' }}）
        </p>
        <p class="trial-source">
          绑定原文：样本 {{ current.样本批次 }} · rev{{ current.内容版本 }}
        </p>
        <pre class="trial-raw" data-testid="retest-raw">{{ current.绑定原文 }}</pre>

        <table class="data-table">
          <thead>
            <tr>
              <th>价格字段</th>
              <th>{{ current.版本A }}</th>
              <th>{{ current.版本B }}</th>
              <th>对照结论</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in fieldRows" :key="row.字段" :data-testid="`retest-field-${row.字段}`">
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

        <div class="page-actions">
          <button class="btn ghost" type="button" data-testid="close-retest" @click="current = null">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { listRetests } from '@/api/parser-review'
import type { RetestRecord, TrialFieldRow } from '@/api/parser-review'

const records = ref<RetestRecord[]>([])
const current = ref<RetestRecord | null>(null)

const fieldRows = computed<TrialFieldRow[]>(() => {
  if (!current.value) return []
  try {
    return JSON.parse(current.value.价格字段差异 || '[]') as TrialFieldRow[]
  } catch {
    return []
  }
})

async function reload() {
  const payload = await listRetests()
  records.value = payload.items
}

function openRecord(record: RetestRecord) {
  current.value = record
}

onMounted(reload)
</script>
