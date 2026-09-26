<template>
  <section class="page" data-module="report">
    <header class="page-head">
      <div>
        <h2>检测报告管理</h2>
        <p class="page-desc">维护检测报告，围绕报告编号、委托单位、样品名称、报告类型做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记检测报告</button>
        <button class="btn" type="button" @click="exportRows">导出检测报告清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
      <article v-if="statsState === 'error'" class="stat-card stat-card-retry">
        <span class="stat-label error-text">数量指标读取失败</span>
        <button class="link" type="button" @click="loadStats">重试</button>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="applyFilters">
      <label class="filter-item">
        <span>报告编号</span>
        <input v-model="filters.keyword" placeholder="按报告编号检索" />
      </label>
      <label class="filter-item">
        <span>委托单位</span>
        <input v-model="filters.client" placeholder="按委托单位检索" />
      </label>
      <label class="filter-item">
        <span>样品名称</span>
        <input v-model="filters.sample" placeholder="按样品名称检索" />
      </label>
      <label class="filter-item">
        <span>报告状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit" :disabled="listState === 'loading'">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="listState === 'loading'">
          <td :colspan="columns.length + 1" class="state-state">检测报告清单加载中…</td>
        </tr>
        <tr v-else-if="listState === 'error'">
          <td :colspan="columns.length + 1" class="state-state">
            <span class="error-text">{{ listError }}</span>
            <button class="btn" type="button" @click="retryList">重试</button>
          </td>
        </tr>
        <tr v-else-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">
            <template v-if="hasActiveFilters">没有符合条件的检测报告</template>
            <template v-else>暂无检测报告数据，可先登记检测报告</template>
            <span class="state-actions">
              <button v-if="hasActiveFilters" class="btn" type="button" @click="resetFilters">重置筛选条件</button>
              <button v-else class="btn primary" type="button" @click="openCreate">登记检测报告</button>
            </span>
          </td>
        </tr>
        <tr v-for="(row, index) in rows" v-else :key="rowKey(row, index)">
          <td v-for="column in columns" :key="column">
            <span v-if="column === '报告编号'">
              {{ cellText(row[column]) }}
              <span v-if="row.abnormal === true" class="badge-abnormal">异常</span>
            </span>
            <span v-else>{{ cellText(row[column]) }}</span>
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">查看详情</button>
            <template v-if="hasValidId(row)">
              <button
                v-for="action in actions"
                :key="action"
                class="link"
                type="button"
                :disabled="pendingActionId === row.id"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </template>
            <span v-else class="error-text">记录编号异常，动作不可用</span>
          </td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span v-if="listState === 'ready'">共 {{ total }} 条检测报告记录 · 第 {{ page }} / {{ totalPages }} 页</span>
      <span v-else>共 — 条检测报告记录</span>
      <span class="foot-side">
        <label class="size-picker">
          每页
          <select v-model.number="size" @change="changeSize">
            <option v-for="option in sizeOptions" :key="option" :value="option">{{ option }}</option>
          </select>
          条
        </label>
        <button class="btn" type="button" :disabled="page <= 1 || listState !== 'ready'" @click="gotoPage(page - 1)">上一页</button>
        <button
          class="btn"
          type="button"
          :disabled="page >= totalPages || listState !== 'ready'"
          @click="gotoPage(page + 1)"
        >下一页</button>
        <span v-if="actionMessage" :class="actionOk ? 'ok-text' : 'error-text'">{{ actionMessage }}</span>
      </span>
    </footer>

    <div v-if="detail.open" class="modal-mask" @click.self="closeDetail">
      <section class="modal-panel" role="dialog" aria-modal="true" aria-label="检测报告详情">
        <header class="modal-head">
          <h3>检测报告详情</h3>
          <button class="btn ghost" type="button" @click="closeDetail">关闭</button>
        </header>
        <div v-if="detail.state === 'loading'" class="modal-body state-state">报告详情加载中…</div>
        <div v-else-if="detail.state === 'error'" class="modal-body state-state">
          <span class="error-text">{{ detail.message }}</span>
          <button class="btn" type="button" @click="retryDetail">重试</button>
        </div>
        <div v-else-if="detail.state === 'notfound'" class="modal-body state-state">
          <span>{{ detail.message }}</span>
          <button class="btn" type="button" @click="closeDetail">关闭</button>
        </div>
        <dl v-else class="detail-grid">
          <template v-for="column in detailFields" :key="column">
            <dt>{{ column }}</dt>
            <dd>{{ cellText(detail.data?.[column]) }}</dd>
          </template>
          <dt>异常标记</dt>
          <dd>
            <span v-if="detail.data?.abnormal === true" class="badge-abnormal">异常</span>
            <span v-else>正常</span>
          </dd>
        </dl>
      </section>
    </div>

    <div v-if="create.open" class="modal-mask" @click.self="closeCreate">
      <section class="modal-panel" role="dialog" aria-modal="true" aria-label="登记检测报告">
        <header class="modal-head">
          <h3>登记检测报告</h3>
          <button class="btn ghost" type="button" @click="closeCreate">取消</button>
        </header>
        <form class="modal-body create-form" @submit.prevent="submitCreate">
          <label v-for="field in createFields" :key="field.key" class="create-item">
            <span>{{ field.label }}<em v-if="field.required">*</em></span>
            <input v-model="create.form[field.key]" :placeholder="`请输入${field.label}`" />
          </label>
          <p v-if="create.errors.length" class="error-text create-error">请补全必填信息后再提交：{{ create.errors.join('、') }}</p>
          <p v-else-if="create.serverError" class="error-text create-error">{{ create.serverError }}</p>
          <footer class="modal-foot">
            <button class="btn" type="button" @click="closeCreate">取消</button>
            <button class="btn primary" type="submit" :disabled="create.submitting">
              {{ create.submitting ? '提交中…' : '确认登记' }}
            </button>
          </footer>
        </form>
      </section>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, unknown>
type LoadState = 'loading' | 'ready' | 'error'
type DetailState = 'loading' | 'ready' | 'error' | 'notfound'

interface StatCard {
  label: string
  value: string
}

const ENDPOINT = '/api/report'
const columns = ["报告编号", "委托单位", "样品名称", "报告类型", "编制人", "批准人", "签发日期", "报告状态"]
const detailFields = ["报告编号", "委托单位", "样品名称", "报告类型", "编制人", "批准人", "签发日期", "报告状态"]
const actions = ["编制报告", "提交批准", "撤回报告"]
const statuses = ["待编制", "编制中", "待批准", "已签发", "已撤回"]
const sizeOptions = [10, 20, 50, 100, 200]
const createFields = [
  { key: "报告编号", label: "报告编号", required: true },
  { key: "委托单位", label: "委托单位", required: true },
  { key: "样品名称", label: "样品名称", required: true },
  { key: "报告类型", label: "报告类型", required: false },
  { key: "编制人", label: "编制人", required: false },
  { key: "批准人", label: "批准人", required: false },
  { key: "签发日期", label: "签发日期", required: false },
] as const
const requiredKeys = ["报告编号", "委托单位", "样品名称"]

const rows = ref<Row[]>([])
const total = ref(0)
const page = ref(1)
const size = ref(20)
const totalPages = computed(() => Math.max(Math.ceil(total.value / size.value), 1))

const listState = ref<LoadState>('loading')
const listError = ref('')
const pendingActionId = ref<unknown>(null)
const actionMessage = ref('')
const actionOk = ref(false)

const statsState = ref<LoadState>('loading')
const statsData = ref<Record<string, number>>({})
const statCards = computed<StatCard[]>(() => {
  const labels = ["待编制报告", "待批准报告", "本月签发"]
  return labels.map((label) => ({
    label,
    value: statsState.value === 'ready' ? String(statsData.value[label] ?? 0) : statsState.value === 'error' ? '—' : '…',
  }))
})

const filters = reactive({ keyword: '', client: '', sample: '', status: '' })
const hasActiveFilters = computed(() =>
  Boolean(filters.keyword.trim() || filters.client.trim() || filters.sample.trim() || filters.status),
)

interface DetailStateRef {
  open: boolean
  id: number | null
  state: DetailState
  data: Row | null
  message: string
}

const detail = reactive<DetailStateRef>({ open: false, id: null, state: 'loading', data: null, message: '' })

interface CreateState {
  open: boolean
  submitting: boolean
  serverError: string
  errors: string[]
  form: Record<string, string>
}

const create = reactive<CreateState>({
  open: false,
  submitting: false,
  serverError: '',
  errors: [],
  form: {},
})

function cellText(value: unknown): string {
  if (value === null || value === undefined) return '—'
  const text = String(value).trim()
  return text ? text : '—'
}

function hasValidId(row: Row): boolean {
  const id = Number(row.id)
  return Number.isInteger(id) && id > 0
}

function rowKey(row: Row, index: number): string {
  return hasValidId(row) ? String(row.id) : `invalid-${index}`
}

function buildQuery(): string {
  const params = new URLSearchParams()
  params.set('page', String(page.value))
  params.set('size', String(size.value))
  if (filters.keyword.trim()) params.set('keyword', filters.keyword.trim())
  if (filters.client.trim()) params.set('client', filters.client.trim())
  if (filters.sample.trim()) params.set('sample', filters.sample.trim())
  if (filters.status) params.set('status', filters.status)
  return params.toString()
}

async function loadList(): Promise<void> {
  listState.value = 'loading'
  listError.value = ''
  try {
    const response = await request(`${ENDPOINT}?${buildQuery()}`)
    if (!response.ok) {
      const detail = await readErrorDetail(response)
      throw new Error(detail || `检测报告列表读取失败（${response.status}），可重试恢复`)
    }
    const payload: unknown = await response.json()
    const items = extractItems(payload)
    const payloadTotal = Number((payload as Record<string, unknown>)?.total)
    total.value = Number.isFinite(payloadTotal) ? payloadTotal : items.length
    rows.value = items
    // 请求页码超出范围（例如删到只剩一条）时回到最后一页，不把空页当成空库。
    if (!items.length && total.value > 0 && page.value > 1) {
      page.value = totalPages.value

      await loadList()
      return
    }
    listState.value = 'ready'
  } catch (error) {
    // 失败时清空旧清单，避免用户对着过期内容继续操作。
    rows.value = []
    total.value = 0
    listState.value = 'error'
    listError.value = error instanceof Error ? error.message : '检测报告列表读取失败，请重试'
  }
}

function extractItems(payload: unknown): Row[] {
  const items = (payload as Record<string, unknown> | null)?.items
  return Array.isArray(items) ? (items as Row[]) : []
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const payload: unknown = await response.json()
    const detail = (payload as Record<string, unknown> | null)?.detail
    return typeof detail === 'string' ? detail : ''
  } catch {
    return ''
  }
}

async function loadStats(): Promise<void> {
  statsState.value = 'loading'
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) {
      throw new Error(`数量指标读取失败（${response.status}）`)
    }
    const payload: unknown = await response.json()
    statsData.value = (payload ?? {}) as Record<string, number>
    statsState.value = 'ready'
  } catch {
    statsState.value = 'error'
  }
}

async function refreshAll(): Promise<void> {
  await Promise.all([loadList(), loadStats()])
  if (detail.open && detail.id !== null) {
    await loadDetail(detail.id)
  }
}

function retryList(): void {
  void refreshAll()
}

function applyFilters(): void {
  page.value = 1
  void loadList()
}

function resetFilters(): void {
  filters.keyword = ''
  filters.client = ''
  filters.sample = ''
  filters.status = ''
  page.value = 1
  void loadList()
}

function gotoPage(target: number): void {
  page.value = Math.min(Math.max(target, 1), totalPages.value)
  void loadList()
}

function changeSize(): void {
  page.value = 1
  void loadList()
}

function exportRows(): void {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate(): void {
  create.open = true
  create.submitting = false
  create.serverError = ''
  create.errors = []
  create.form = {}
}

function closeCreate(): void {
  create.open = false
}

async function submitCreate(): Promise<void> {
  const form = create.form
  create.errors = requiredKeys.filter((key) => !form[key]?.trim())
  create.serverError = ''
  if (create.errors.length) {
    // 输入不完整：停留在弹窗内提示，用户补齐后可再次提交。
    return
  }
  create.submitting = true
  try {
    const values: Record<string, string> = {}
    for (const field of createFields) {
      const text = form[field.key]?.trim()
      if (text) values[field.key] = text
    }
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload: unknown = await response.json().catch(() => null)
    const result = (payload ?? {}) as { ok?: boolean; message?: string }
    if (!response.ok || result.ok === false) {
      // 编号重复等业务拒绝：保留已填内容，允许修改后重试，不产生覆盖。
      create.serverError = result.message || '检测报告登记失败，请调整后重试'
      return
    }
    create.open = false
    page.value = 1
    await refreshAll()
    setActionMessage(result.message || '检测报告已登记', true)
  } catch (error) {
    create.serverError = error instanceof Error ? error.message : '检测报告登记失败，请重试'
  } finally {
    create.submitting = false
  }
}

async function runAction(action: string, row: Row): Promise<void> {
  const id = Number(row.id)
  if (!Number.isInteger(id) || id <= 0) return
  pendingActionId.value = row.id
  actionMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload: unknown = await response.json().catch(() => null)
    const result = (payload ?? {}) as { ok?: boolean; message?: string }
    if (!response.ok || result.ok === false) {
      setActionMessage(result.message || '检测报告动作未生效，请稍后重试', false)
      return
    }
    await refreshAll()
    setActionMessage(result.message || '检测报告状态已更新', true)
  } catch (error) {
    setActionMessage(error instanceof Error ? error.message : '检测报告操作失败，请稍后重试', false)
  } finally {
    pendingActionId.value = null
  }
}

function setActionMessage(message: string, ok: boolean): void {
  actionMessage.value = message
  actionOk.value = ok
}

function openDetail(row: Row): void {
  if (!hasValidId(row)) {
    setActionMessage('该记录缺少有效报告编号标识，详情暂不可读', false)
    return
  }
  void loadDetail(Number(row.id))
}

async function loadDetail(id: number): Promise<void> {
  detail.open = true
  detail.id = id
  detail.state = 'loading'
  detail.data = null
  detail.message = ''
  try {
    const response = await request(`${ENDPOINT}/${id}`)
    if (response.status === 404) {
      detail.state = 'notfound'
      detail.message = `检测报告 ${id} 不存在或已归档`
      return
    }
    if (!response.ok) {
      throw new Error(`报告详情读取失败（${response.status}），可重试恢复`)
    }
    detail.data = (await response.json()) as Row
    detail.state = 'ready'
  } catch (error) {
    detail.state = 'error'
    detail.message = error instanceof Error ? error.message : '报告详情读取失败，请重试'
  }
}

function retryDetail(): void {
  if (detail.id !== null) {
    void loadDetail(detail.id)
  }
}

function closeDetail(): void {
  detail.open = false
  detail.id = null
  detail.data = null
  detail.state = 'loading'
  detail.message = ''
}

onMounted(() => {
  void Promise.all([loadList(), loadStats()])
})
</script>

<style scoped>
.state-state {
  text-align: center;
  color: var(--muted);
  vertical-align: middle;
}
.state-state .btn {
  margin-left: 10px;
}
.state-actions {
  display: block;
  margin-top: 8px;
}
.stat-card-retry {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
  max-width: 180px;
}
.badge-abnormal {
  display: inline-block;
  margin-left: 6px;
  padding: 0 6px;
  border-radius: 4px;
  background: #fef3f2;
  color: #b42318;
  border: 1px solid #fda29b;
  font-size: 11px;
  line-height: 16px;
}
.foot-side {
  display: flex;
  align-items: center;
  gap: 8px;
}
.size-picker {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.ok-text {
  color: #067647;
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(16, 24, 40, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal-panel {
  width: min(640px, 92vw);
  max-height: 84vh;
  overflow: auto;
  background: #fff;
  border-radius: 10px;
  border: 1px solid var(--border);
}
.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}
.modal-head h3 {
  margin: 0;
  font-size: 15px;
}
.modal-body {
  padding: 16px;
}
.detail-grid {
  display: grid;
  grid-template-columns: 96px 1fr;
  gap: 8px 12px;
  margin: 0;
  font-size: 13px;
}
.detail-grid dt {
  color: var(--muted);
}
.detail-grid dd {
  margin: 0;
}
.create-form {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 14px;
}
.create-item span {
  display: block;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 4px;
}
.create-item em {
  color: #b42318;
  font-style: normal;
  margin-left: 2px;
}
.create-item input {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.create-error {
  grid-column: 1 / -1;
  margin: 0;
  font-size: 12px;
}
.modal-foot {
  grid-column: 1 / -1;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
