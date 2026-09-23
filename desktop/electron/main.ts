import { app, BrowserWindow, ipcMain, shell } from 'electron'
import { spawn, type ChildProcessByStdio } from 'node:child_process'
import http from 'node:http'
import type { Readable } from 'node:stream'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// The built directory structure
//
// ├─┬─┬ dist
// │ │ └── index.html
// │ │
// │ ├─┬ dist-electron
// │ │ ├── main.js
// │ │ └── preload.mjs
// │
process.env.APP_ROOT = path.join(__dirname, '..')

// 🚧 Use ['ENV_NAME'] avoid vite:define plugin - Vite@2.x
export const VITE_DEV_SERVER_URL = process.env['VITE_DEV_SERVER_URL']
export const MAIN_DIST = path.join(process.env.APP_ROOT, 'dist-electron')
export const RENDERER_DIST = path.join(process.env.APP_ROOT, 'dist')

process.env.VITE_PUBLIC = VITE_DEV_SERVER_URL
  ? path.join(process.env.APP_ROOT, 'public')
  : RENDERER_DIST

const REPO_ROOT = path.resolve(process.env.APP_ROOT, '..')
const BACKEND_HOST = process.env.GHOSTJOB_HOST || '127.0.0.1'
const BACKEND_PORT = Number(process.env.GHOSTJOB_PORT || 8765)

let win: BrowserWindow | null = null
let backendProcess: ChildProcessByStdio<null, Readable, Readable> | null = null

function backendHttpUrl() {
  return `http://${BACKEND_HOST}:${BACKEND_PORT}`
}

function backendWsUrl() {
  return `ws://${BACKEND_HOST}:${BACKEND_PORT}/ws`
}

function resolvePythonCommand(): { command: string; args: string[] } {
  if (process.env.GHOSTJOB_PYTHON) {
    return { command: process.env.GHOSTJOB_PYTHON, args: ['main.py'] }
  }
  return { command: 'uv', args: ['run', 'python', 'main.py'] }
}

function waitForHealth(timeoutMs = 20000): Promise<void> {
  const started = Date.now()
  return new Promise((resolve, reject) => {
    const tick = () => {
      const req = http.get(`${backendHttpUrl()}/health`, (res) => {
        res.resume()
        if (res.statusCode === 200) {
          resolve()
          return
        }
        retry()
      })
      req.on('error', retry)
      req.setTimeout(1000, () => {
        req.destroy()
        retry()
      })
    }

    const retry = () => {
      if (Date.now() - started > timeoutMs) {
        reject(new Error(`backend health check timed out on ${backendHttpUrl()}`))
        return
      }
      setTimeout(tick, 250)
    }

    tick()
  })
}

function startBackend(): Promise<void> {
  if (backendProcess) return waitForHealth()

  const { command, args } = resolvePythonCommand()
  console.log(`[ghostjob] starting backend: ${command} ${args.join(' ')} (cwd=${REPO_ROOT})`)

  backendProcess = spawn(command, args, {
    cwd: REPO_ROOT,
    env: {
      ...process.env,
      GHOSTJOB_HOST: BACKEND_HOST,
      GHOSTJOB_PORT: String(BACKEND_PORT),
      PYTHONUNBUFFERED: '1',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  })

  backendProcess.stdout.on('data', (buf: Buffer) => {
    process.stdout.write(`[backend] ${buf.toString()}`)
  })
  backendProcess.stderr.on('data', (buf: Buffer) => {
    process.stderr.write(`[backend] ${buf.toString()}`)
  })
  backendProcess.on('exit', (code, signal) => {
    console.log(`[ghostjob] backend exited code=${code} signal=${signal}`)
    backendProcess = null
  })

  return waitForHealth()
}

function stopBackend() {
  if (!backendProcess) return
  const child = backendProcess
  backendProcess = null
  try {
    child.kill('SIGTERM')
  } catch {
    // ignore
  }
}

function createWindow() {
  win = new BrowserWindow({
    width: 960,
    height: 720,
    title: 'Ghostjob',
    icon: path.join(process.env.VITE_PUBLIC, 'electron-vite.svg'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.mjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  win.webContents.on('did-finish-load', () => {
    win?.webContents.send('main-process-message', new Date().toLocaleString())
  })

  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http:') || url.startsWith('https:')) {
      void shell.openExternal(url)
    }
    return { action: 'deny' }
  })

  if (VITE_DEV_SERVER_URL) {
    win.loadURL(VITE_DEV_SERVER_URL)
  } else {
    win.loadFile(path.join(RENDERER_DIST, 'index.html'))
  }
}

ipcMain.handle('ghostjob:get-backend-ws-url', () => backendWsUrl())
ipcMain.handle('ghostjob:get-backend-http-url', () => backendHttpUrl())

app.whenReady().then(async () => {
  try {
    await startBackend()
    console.log(`[ghostjob] backend ready at ${backendHttpUrl()}`)
  } catch (err) {
    console.error('[ghostjob] failed to start backend', err)
  }

  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

app.on('window-all-closed', () => {
  stopBackend()
  if (process.platform !== 'darwin') {
    app.quit()
    win = null
  }
})

app.on('before-quit', () => {
  stopBackend()
})
