# Ghostjob Reflex 迁移（去掉 Electron）

## 目标

用 **Reflex** 替换 Electron + Vue 桌面壳与 FastAPI WebSocket 网关；UI 与 `BossSession` 同进程，直接驱动抓取（含滚动加载与停止）。

## 架构

```text
uv run reflex run
    └── ghostjob/          # Reflex App + State
            └── 直接调用 backend.boss.session.BossSession
                    └── Patchright Chrome (~/.ghostjob/chrome-profile)
```

### 删除

- `desktop/`（Electron + Vue + electron-vite）
- `backend/server.py`（FastAPI `/health` + `/ws`）
- `main.py` 中以 uvicorn 启动后端的入口（改为 Reflex 入口）
- 依赖与测试中仅服务于 WS/Electron 的部分（如 `tests/boss/test_ws_boss.py`）

### 保留

- `backend/boss/jobs.py`（解析、模型、`print_job`）
- `backend/boss/session.py`（Patchright 会话；扩展滚动/停止）
- 现有 boss 离线/单元测试（`test_jobs_parse.py`、`test_session_unit.py`）

## UI（对标现有 Vue）

`rx.State` 字段：

| 字段 | 含义 |
|------|------|
| `boss_state` | 状态文案（ready / navigating / scraping / stopped / done / need_login / error…） |
| `busy` | 操作进行中，禁用互斥按钮 |
| `jobs` | 职位列表（扁平时字段，与原 WS `job_to_dict` 一致） |
| `log` | 最近若干条操作日志 |

按钮：

- **打开 BOSS** → `BossSession.open()`
- **抓列表+详情** → 后台任务跑 `search`（滚动循环）
- **停止** → 置 `stop_requested`；本卡结束后退出循环
- **关闭** → `BossSession.close()`

列表展示：标题、薪资、公司、地点、经验、学历、HR 姓名/职务、详细地址、职位描述；标题可链到职位 URL。

## 抓取：滚动 + 停止

1. 打开搜索页，拦截 `joblist.json`，抓当前可见卡片（含详情：JD / HR / 地址）。
2. 滚到列表底部，等待新一批（`joblist.json` 或 DOM 卡片数增加）。
3. 仅处理 **新增** 卡片（按 `jobId` 去重）。
4. 循环直到任一条件：
   - UI 触发停止（`stop_requested`）
   - 连续 2 次滚动无新增
   - 达到批次上限（默认 **20**）
5. 每张卡仍 `print_job` 到 stdout；UI 侧在批次结束或每张完成后更新 `jobs`（实现时优先：**每处理完一张或每批追加**，保证点停止时界面已有结果）。

`BossSession.search`（或等价 API）需支持：

- 可协作取消（检查 stop flag / `asyncio.Event`）
- 返回已抓取的全部 `list[Job]` 与终态：`done` | `stopped` | `need_login`

## 工程与入口

| 项 | 做法 |
|----|------|
| Reflex 应用 | 仓库根：`rxconfig.py` + 包目录（建议 `ghostjob/`：`ghostjob.py` / `state.py` / 组件） |
| 依赖 | 保留 `reflex`、`patchright`、`pyquery`；移除不再使用的 `fastapi[standard]`（若无其它引用） |
| 启动 | `uv sync` 后 `uv run reflex run`；README 改为 Reflex 说明 |
| 脚本 | `[project.scripts]` 从 `ghostjob-backend` 改为 Reflex 友好入口（或 README 只写 `reflex run`） |

## 测试策略

- 保留并扩展 `jobs` / `session` 单测（滚动去重、stop flag 逻辑尽量可单测的纯函数分离）
- 删除或改写依赖 FastAPI TestClient / WebSocket 的测试
- 不做 Electron E2E

## 非目标

- NiceGUI / pywebview
- 翻页控件、改搜索条件 UI、自动登录轮询
- 无头 Chrome、多账号

## 风险与约定

- Reflex 后台长任务需用官方 **background** 事件，避免阻塞 UI 事件循环。
- Patchright 弹窗 Chrome 与 Reflex 浏览器 UI 并存：用户在 Chrome 登录，在 Reflex 页点控制。
- 首次迁移以功能对齐为准，视觉不追求像素级复刻 Vue。

## 实现状态

- [ ] 已实现（Reflex 迁移 Tasks 1–4 完成后勾选）
