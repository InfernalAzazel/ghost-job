# ghostjob

Electron（electron-vite）+ Vue + Python 桌面壳。

## 架构

```text
desktop/electron/main.ts  --spawn-->  uv run python main.py (:8765)
              |
              v
desktop/src (Vue)  --WebSocket /ws-->  backend/server.py
```

## 开发

```bash
# 仓库根目录
uv sync

# Reflex UI（迁移中）
uv run reflex run

# 桌面端（Electron + Vue，逐步退役）
cd desktop
npm install
npm run dev
```

窗口显示「已连接」后，点 **Ping** 应收到 `pong`。

## BOSS 列表（v1）

用 Patchright 拉起本机 Google Chrome（独立 profile：`~/.ghostjob/chrome-profile`），无需调试端口。

1. 安装本机 Google Chrome。
2. `uv sync` 后启动桌面或单独后端。
3. 点击「打开 BOSS」→ 在弹出的 Chrome 中登录（首次）。
4. 点击「抓列表+详情」：会依次点击当前页每张职位卡，抓 JD，并在**后端终端**打印。

默认搜索：广州 · AI应用开发（见 `backend/boss/jobs.py` 中 `DEFAULT_SEARCH_URL`）。
退出 Ghostjob 会关闭该自动化 Chrome 窗口，但保留 profile 登录态。

## 单独跑后端

```bash
uv run python main.py
curl http://127.0.0.1:8765/health
```
