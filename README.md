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

# 桌面端
cd desktop
npm install
npm run dev
```

窗口显示「已连接」后，点 **Ping** 应收到 `pong`。

## BOSS 列表（v1）

用 Patchright CDP 附着本机 Chrome（不另开独立 profile）。

1. 完全退出 Chrome 后，用调试端口启动，例如：

    ```bash
    /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
    ```

2. `uv sync` 后启动桌面或单独后端。
3. 点击「连接 Chrome」→「抓列表」。
4. 可选：`GHOSTJOB_CDP_URL` 覆盖默认 `http://127.0.0.1:9222`。

默认搜索：广州 · AI应用开发（见 `backend/boss/jobs.py` 中 `DEFAULT_SEARCH_URL`）。
退出 Ghostjob 不会关闭你的 Chrome。

## 单独跑后端

```bash
uv run python main.py
curl http://127.0.0.1:8765/health
```
