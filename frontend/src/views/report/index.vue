<template>
  <section class="page" data-module="report">
    <header class="page-head">
      <div>
        <h2>检测报告管理</h2>
        <p class="page-desc">维护检测报告，围绕报告编号、委托单位、样品名称、报告类型做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="toggleCreate">
          {{ showCreate ? '收起登记' : '登记检测报告' }}
        </button>
        <button class="btn" type="button" @click="exportRows">导出检测报告清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form v-if="showCreate" class="create-panel" @submit.prevent="submitCreate">
      <label v-for="field in createFields" :key="field.name" class="filter-item">
        <span>{{ field.label }}{{ field.required ? '（必填）' : '' }}</span>
        <input
          v-model="createForm[field.name]"
          :placeholder="field.required ? `请输入${field.label}` : `选填，${field.label}`"
        />
      </label>
      <button class="btn primary" type="submit" :disabled="saving">
        {{ saving ? '提交中…' : '提交登记' }}
      </button>
      <p v-if="createError" class="error-text create-error">{{ createError }}，可修改后重新提交</p>
    </form>

    <form class="filter-bar" @submit.prevent="applyFilters">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody v-if="listState === 'ready'">
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ cellText(row, column) }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">{{ emptyText }}</td>
        </tr>
      </tbody>
      <tbody v-else-if="listState === 'loading'">
        <tr>
          <td :colspan="columns.length + 1" class="empty-state">检测报告加载中…</td>
        </tr>
      </tbody>
      <tbody v-else>
        <tr>
          <td :colspan="columns.length + 1" class="empty-state">
            <span class="error-text">{{ listError }}</span>
            <button class="btn retry-btn" type="button" @click="reload">重试</button>
          </td>
        </tr>
      </tbody>
    </table>

    <section v-if="detailState !== 'hidden'" class="detail-panel">
      <header class="detail-head">
        <h3>检测报告详情{{ detailId !== null ? `（#${detailId}）` : '' }}</h3>
        <button class="btn ghost" type="button" @click="closeDetail">关闭</button>
      </header>
      <p v-if="detailState === 'loading'" class="empty-state">详情加载中…</p>
      <p v-else-if="detailState === 'error'" class="empty-state">
        <span class="error-text">{{ detailError }}</span>
        <button class="btn retry-btn" type="button" @click="retryDetail">重试</button>
      </p>
      <dl v-else class="detail-grid">
        <template v-for="column in columns" :key="column">
          <dt>{{ column }}</dt>
          <dd>{{ cellText(detail ?? {}, column) }}</dd>
        </template>
      </dl>
    </section>

    <footer class="page-foot">
      <span>共 {{ total }} 条检测报告记录</span>
      <span class="pager">
        <button
          class="btn ghost"
          type="button"
          :disabled="page <= 1 || listState !== 'ready'"
          @click="turnPage(-1)"
        >上一页</button>
        <span>第 {{ page }} / {{ pageCount }} 页</span>
        <button
          class="btn ghost"
          type="button"
          :disabled="page >= pageCount || listState !== 'ready'"
          @click="turnPage(1)"
        >下一页</button>
      </span>
      <span v-if="actionError" class="error-text">{{ actionError }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
interface StatItem {
  label: string
  value: number
}
interface ListPayload {
  items?: Row[]
  total?: number
}
interface StatsPayload {
  stats?: StatItem[]
}
interface ActionPayload {
  ok?: boolean
  message?: string
}

const ENDPOINT = '/api/report'
const PAGE_SIZE = 20
const columns = ["报告编号", "委托单位", "样品名称", "报告类型", "编制人", "批准人", "签发日期", "报告状态"]
const actions = ["编制报告", "提交批准", "撤回报告"]
const filterFields = columns.slice(0, 3)
const createFields = [
  { name: '报告编号', label: '报告编号', required: true },
  { name: '委托单位', label: '委托单位', required: true },
  { name: '样品名称', label: '样品名称', required: true },
  { name: '报告类型', label: '报告类型', required: false },
  { name: '编制人', label: '编制人', required: false },
  { name: '批准人', label: '批准人', required: false },
  { name: '签发日期', label: '签发日期', required: false },
]
const statLabels = ["待编制报告", "待批准报告", "本月签发"]

function zeroStats(): StatItem[] {
  return statLabels.map((label) => ({ label, value: 0 }))
}

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref<StatItem[]>(zeroStats())
const listState = ref<'loading' | 'error' | 'ready'>('loading')
const listError = ref('')
const actionError = ref('')
const page = ref(1)
const filters = reactive<Record<string, string>>({})

const showCreate = ref(false)
const createForm = reactive<Record<string, string>>({})
const createError = ref('')
const saving = ref(false)

const detail = ref<Row | null>(null)
const detailState = ref<'hidden' | 'loading' | 'error' | 'ready'>('hidden')
const detailError = ref('')
const detailId = ref<number | null>(null)

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))
const hasFilters = computed(() => filterFields.some((field) => (filters[field] ?? '').trim() !== ''))
const emptyText = computed(() =>
  hasFilters.value
    ? '当前筛选条件下没有检测报告，可重置条件后再试'
    : '暂无检测报告数据，可先登记检测报告',
)

function cellText(row: Row, column: string): string {
  const value = row?.[column]
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}

async function fetchPayload<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await request(path, init)
  const payload: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = (payload as { detail?: unknown } | null)?.detail
    if (typeof detail === 'string' && detail.trim()) {
      throw new Error(detail)
    }
    throw new Error(`接口返回 ${response.status}，请稍后重试`)
  }
  return payload as T
}

function normalizeStats(payload: StatsPayload | null): StatItem[] {
  const incoming = Array.isArray(payload?.stats) ? payload.stats : []
  return statLabels.map((label) => {
    const hit = incoming.find((item) => item && item.label === label)
    const value = Number(hit?.value)
    return { label, value: Number.isFinite(value) ? value : 0 }
  })
}

let reloadSeq = 0

async function reload() {
  const seq = ++reloadSeq
  listState.value = 'loading'
  listError.value = ''
  const params = new URLSearchParams()
  for (const field of filterFields) {
    const value = (filters[field] ?? '').trim()
    if (value) params.set(field, value)
  }
  params.set('page', String(page.value))
  params.set('size', String(PAGE_SIZE))
  try {
    const [listPayload, statsPayload] = await Promise.all([
      fetchPayload<ListPayload>(`${ENDPOINT}?${params.toString()}`),
      fetchPayload<StatsPayload>(`${ENDPOINT}/stats`),
    ])
    if (seq !== reloadSeq) return
    rows.value = Array.isArray(listPayload?.items) ? listPayload.items : []
    total.value = typeof listPayload?.total === 'number' ? listPayload.total : rows.value.length
    stats.value = normalizeStats(statsPayload)
    listState.value = 'ready'
  } catch (error) {
    if (seq !== reloadSeq) return
    // 失败时清空旧内容，避免把过期清单当成当前数据展示
    rows.value = []
    total.value = 0
    stats.value = zeroStats()
    listError.value = error instanceof Error ? error.message : '检测报告列表读取失败'
    listState.value = 'error'
  }
}

function applyFilters() {
  page.value = 1
  void reload()
}

function resetFilters() {
  for (const field of filterFields) filters[field] = ''
  page.value = 1
  void reload()
}

function turnPage(delta: number) {
  const next = page.value + delta
  if (next < 1 || next > pageCount.value) return
  page.value = next
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function toggleCreate() {
  showCreate.value = !showCreate.value
  createError.value = ''
}

async function submitCreate() {
  createError.value = ''
  const missing = createFields
    .filter((field) => field.required && !(createForm[field.name] ?? '').trim())
    .map((field) => field.label)
  if (missing.length) {
    createError.value = `请先补充：${missing.join('、')}`
    return
  }
  saving.value = true
  try {
    const values: Record<string, string> = {}
    for (const field of createFields) {
      values[field.name] = (createForm[field.name] ?? '').trim()
    }
    const payload = await fetchPayload<ActionPayload>(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    if (!payload?.ok) {
      throw new Error(payload?.message || '检测报告登记失败，请稍后重试')
    }
    showCreate.value = false
    for (const field of createFields) createForm[field.name] = ''
    page.value = 1
    await reload()
  } catch (error) {
    // 表单内容保留，允许直接修改后重试
    createError.value = error instanceof Error ? error.message : '检测报告登记失败，请稍后重试'
  } finally {
    saving.value = false
  }
}

async function runAction(action: string, row: Row) {
  actionError.value = ''
  try {
    const payload = await fetchPayload<ActionPayload>(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    if (!payload?.ok) {
      throw new Error(payload?.message || '检测报告动作未生效，请稍后重试')
    }
    await reload()
    if (detailState.value !== 'hidden' && detailId.value === Number(row.id)) {
      await refreshDetail()
    }
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '检测报告操作失败'
  }
}

function openDetail(row: Row) {
  detailId.value = Number(row.id)
  detail.value = null
  void refreshDetail()
}

async function refreshDetail() {
  if (detailId.value === null) return
  detailState.value = 'loading'
  detailError.value = ''
  try {
    detail.value = await fetchPayload<Row>(`${ENDPOINT}/${detailId.value}`)
    detailState.value = 'ready'
  } catch (error) {
    detail.value = null
    detailError.value = error instanceof Error ? error.message : '检测报告详情读取失败'
    detailState.value = 'error'
  }
}

function retryDetail() {
  void refreshDetail()
}

function closeDetail() {
  detailState.value = 'hidden'
  detail.value = null
  detailId.value = null
}

onMounted(reload)
</script>
