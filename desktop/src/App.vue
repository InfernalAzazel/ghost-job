<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

type BossJob = {
  title: string
  company: string
  salary: string
  link: string
  jobId?: string | null
}

type WsInbound = {
  type?: string
  time?: string
  state?: string
  message?: string
  jobs?: BossJob[]
  url?: string
  code?: string
}

const status = ref<'connecting' | 'connected' | 'disconnected'>('connecting')
const lastPong = ref('')
const log = ref<string[]>([])
const wsUrl = ref('ws://127.0.0.1:8765/ws')

const bossState = ref('—')
const bossJobs = ref<BossJob[]>([])
const bossBusy = ref(false)

let socket: WebSocket | null = null

const statusLabel = computed(() => {
  if (status.value === 'connected') return '已连接'
  if (status.value === 'connecting') return '连接中…'
  return '未连接'
})

function pushLog(line: string) {
  const stamp = new Date().toLocaleTimeString()
  log.value = [`[${stamp}] ${line}`, ...log.value].slice(0, 20)
}

function sendBoss(type: 'boss.open' | 'boss.search' | 'boss.close') {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    pushLog(`${type} skipped: not connected`)
    return
  }
  const payload = JSON.stringify({ type })
  socket.send(payload)
  pushLog(`→ ${payload}`)
}

function handleWsMessage(data: WsInbound) {
  if (data.type === 'pong') {
    lastPong.value = data.time || ''
    return
  }
  if (data.type === 'boss.status') {
    if (data.state === 'error') {
      bossState.value = data.message ? `error: ${data.message}` : data.state || ''
    } else {
      bossState.value = data.state || ''
    }
    if (data.state === 'navigating' || data.state === 'launching') bossBusy.value = true
    if (
      data.state === 'done' ||
      data.state === 'need_login' ||
      data.state === 'error' ||
      data.state === 'ready'
    ) {
      bossBusy.value = false
    }
    return
  }
  if (data.type === 'boss.jobs' && Array.isArray(data.jobs)) {
    bossJobs.value = data.jobs
    return
  }
  if (data.type === 'boss.error') {
    bossState.value = `error: ${data.message || ''}`
    bossBusy.value = false
  }
}

function connect() {
  status.value = 'connecting'
  pushLog(`connecting ${wsUrl.value}`)
  socket?.close()
  socket = new WebSocket(wsUrl.value)

  socket.onopen = () => {
    status.value = 'connected'
    pushLog('websocket open')
  }

  socket.onmessage = (event) => {
    pushLog(`← ${event.data}`)
    try {
      const data = JSON.parse(String(event.data)) as WsInbound
      handleWsMessage(data)
    } catch {
      // ignore
    }
  }

  socket.onclose = () => {
    status.value = 'disconnected'
    pushLog('websocket closed')
  }

  socket.onerror = () => {
    status.value = 'disconnected'
    pushLog('websocket error')
  }
}

function ping() {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    pushLog('ping skipped: not connected')
    return
  }
  const payload = JSON.stringify({ type: 'ping', data: 'ghostjob' })
  socket.send(payload)
  pushLog(`→ ${payload}`)
}

onMounted(async () => {
  try {
    if (window.ghostjob?.getBackendWsUrl) {
      wsUrl.value = await window.ghostjob.getBackendWsUrl()
    }
  } catch (err) {
    pushLog(`preload ws url failed: ${String(err)}`)
  }
  connect()
})

onUnmounted(() => {
  socket?.close()
})
</script>

<template>
  <main class="shell">
    <header>
      <h1>Ghostjob</h1>
      <p class="sub">Electron + Vue + Python</p>
    </header>

    <section class="panel">
      <div class="row">
        <span class="label">状态</span>
        <span class="value" :data-status="status">{{ statusLabel }}</span>
      </div>
      <div class="row">
        <span class="label">WS</span>
        <span class="value mono">{{ wsUrl }}</span>
      </div>
      <div class="row">
        <span class="label">最近 pong</span>
        <span class="value mono">{{ lastPong || '—' }}</span>
      </div>
      <div class="actions">
        <button type="button" :disabled="status !== 'connected'" @click="ping">Ping</button>
        <button type="button" class="ghost" @click="connect">重连</button>
      </div>
    </section>

    <section class="panel">
      <h2>BOSS</h2>
      <div class="row">
        <span class="label">状态</span>
        <span class="value">{{ bossState }}</span>
      </div>
      <div class="actions">
        <button
          type="button"
          :disabled="status !== 'connected' || bossBusy"
          @click="sendBoss('boss.open')"
        >
          连接 Chrome
        </button>
        <button
          type="button"
          :disabled="status !== 'connected' || bossBusy"
          @click="sendBoss('boss.search')"
        >
          抓列表
        </button>
      </div>
      <ul v-if="bossJobs.length" class="jobs">
        <li v-for="(job, i) in bossJobs" :key="job.jobId || i">
          <a :href="job.link" target="_blank" rel="noreferrer">{{ job.title }}</a>
          <span class="meta">{{ job.company }} · {{ job.salary }}</span>
        </li>
      </ul>
    </section>

    <section class="panel log">
      <h2>日志</h2>
      <ul>
        <li v-for="(line, i) in log" :key="i">{{ line }}</li>
      </ul>
    </section>
  </main>
</template>

<style scoped>
.shell {
  width: min(720px, 100%);
  margin: 0 auto;
  text-align: left;
}

header h1 {
  margin: 0;
  font-size: 2rem;
}

.sub {
  margin: 8px 0 24px;
  color: #8b949e;
}

.panel {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  padding: 16px 18px;
  margin-bottom: 14px;
}

.panel h2 {
  margin: 0 0 10px;
  font-size: 1rem;
}

.row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.row:last-of-type {
  border-bottom: none;
}

.label {
  color: #8b949e;
}

.value[data-status='connected'] {
  color: #3fb950;
  font-weight: 600;
}

.value[data-status='connecting'] {
  color: #d29922;
}

.value[data-status='disconnected'] {
  color: #f85149;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.9rem;
}

.actions {
  display: flex;
  gap: 10px;
  margin-top: 14px;
}

button.ghost {
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.jobs {
  list-style: none;
  margin: 14px 0 0;
  padding: 0;
}

.jobs li {
  padding: 10px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.jobs li:last-child {
  border-bottom: none;
}

.jobs a {
  display: block;
  color: #58a6ff;
  text-decoration: none;
  font-weight: 500;
}

.jobs a:hover {
  text-decoration: underline;
}

.meta {
  display: block;
  margin-top: 4px;
  font-size: 0.85rem;
  color: #8b949e;
}

.log h2 {
  margin: 0 0 10px;
  font-size: 1rem;
}

.log ul {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 260px;
  overflow: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.82rem;
}

.log li {
  padding: 4px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

@media (prefers-color-scheme: light) {
  .sub,
  .label,
  .meta {
    color: #57606a;
  }

  .panel {
    background: #f6f8fa;
    border-color: #d0d7de;
  }

  .row,
  .jobs li {
    border-bottom-color: #d8dee4;
  }

  button.ghost {
    border-color: #d0d7de;
  }

  .jobs a {
    color: #0969da;
  }
}
</style>
