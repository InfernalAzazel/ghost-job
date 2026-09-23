/// <reference types="vite-plugin-electron/electron-env" />

declare namespace NodeJS {
  interface ProcessEnv {
    APP_ROOT: string
    VITE_PUBLIC: string
  }
}

interface GhostjobApi {
  getBackendWsUrl: () => Promise<string>
  getBackendHttpUrl: () => Promise<string>
}

interface Window {
  ipcRenderer: import('electron').IpcRenderer
  ghostjob: GhostjobApi
}
