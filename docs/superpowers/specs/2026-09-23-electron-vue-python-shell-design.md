# ghostjob 最小壳设计（Hermes 风格）

## 目标

第一版只跑通桌面壳：Electron 开窗、Vue 页面、Python 独立服务、WebSocket ping/pong。

## 架构

```text
Electron Main  --spawn-->  Python (FastAPI + WebSocket :8765)
     |
     v
Vue (Vite :5173)  --WebSocket-->  Python
```

## 范围

- 做：窗口、健康检查、WS echo、退出时回收子进程
- 不做：投递、Agent、打包安装器、复杂 preload API

## 目录

- `backend/`：Python 服务
- `apps/desktop/`：Electron + Vue
- `main.py`：后端入口（供 Electron spawn）
