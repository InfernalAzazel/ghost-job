# BOSS 直聘列表接入（Patchright + CDP 附着本机 Chrome）

## 目标

第一版用 **Patchright** 通过 **CDP** 附着本机已运行的 Google Chrome（不另开独立 profile 窗口），在现有浏览器里打开 BOSS 搜索页，抓取职位列表，经现有 WebSocket 推到 Electron/Vue 桌面端展示。

默认搜索 URL：

`https://www.zhipin.com/web/geek/jobs?city=101280100&jobType=1901&query=ai应用开发`

## 非目标（v1）

- 职位详情、立即沟通、投递
- 翻页、多账号、无头模式
- 自动轮询登录 / 绕过验证码
- `launch_persistent_context` 另起一套 Chrome / 独立 `user_data_dir`
- Electron 内嵌 BOSS 页面做自动化
- 独立 Worker 进程

## 架构

```text
Vue  --WS /ws-->  FastAPI gateway  --owns-->  BossSession (Patchright)
                                           |
                                    connect_over_cdp
                                           |
                                           v
                         本机已开的 Google Chrome
                         (--remote-debugging-port=9222)
```

| 模块 | 职责 | 不做什么 |
|------|------|----------|
| `backend/boss/session.py` | CDP 连接/断开、导航、关连接（不杀 Chrome） | 不写业务字段解析；不 launch 新浏览器 |
| `backend/boss/jobs.py` | 搜索页列表选择器与字段抽取 | 不进详情、不投递 |
| `backend/server.py` | WS 命令路由、状态/结果推送 | 不直接散落 Patchright 调用 |
| `desktop/src` | 打开连接 / 抓列表按钮、状态、结果列表 | 不直接控浏览器 |

## 浏览器约束

使用 Patchright（Playwright 兼容 API）**附着**已开调试端口的 Chrome：

```python
browser = await playwright.chromium.connect_over_cdp(
    os.environ.get("GHOSTJOB_CDP_URL", "http://127.0.0.1:9222")
)
# 使用已有 context / page；需要时 new_page() 打开搜索页
# 不设置自定义 user_agent / extra_http_headers
```

- 仅对接本机 **Google Chrome**（用户日常浏览器）
- Chrome 须带远程调试启动，默认 CDP：`http://127.0.0.1:9222`（可用环境变量 `GHOSTJOB_CDP_URL` 覆盖）
- macOS 示例（先完全退出 Chrome 再执行）：

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
```

- **不**使用独立 `~/.ghostjob/chrome-profile`；登录态即用户 Chrome 里已有会话
- `boss.close` / 应用退出：只断开 Patchright 的 CDP 连接，**不关闭**用户的 Chrome 进程

## WebSocket 协议

沿用现有 `/ws`，JSON 消息：

| 方向 | `type` | 载荷 |
|------|--------|------|
| 前端 → 后端 | `boss.open` | （可空）连接 CDP；失败则提示如何开调试端口 |
| 前端 → 后端 | `boss.search` | `{ "url"?: string }`；缺省用上述默认搜索 URL |
| 前端 → 后端 | `boss.close` | 断开 CDP 连接（不退出 Chrome） |
| 后端 → 前端 | `boss.status` | `{ "state": "launching\|ready\|navigating\|need_login\|done\|error", "message"?: string }` |
| 后端 → 前端 | `boss.jobs` | `{ "url": string, "jobs": Job[] }` |
| 后端 → 前端 | `boss.error` | `{ "message": string, "code"?: string }` |

`Job` 字段：`title`、`company`、`salary`、`link`，以及能解析到时的 `jobId`。

保留现有 `ping` / `pong` / `echo` / `hello` 行为。

说明：`boss.status` 的 `launching` 在本设计中表示「正在连接 CDP」，不是启动新浏览器。

### 主路径

1. 用户先按文档用调试端口打开本机 Chrome（可已登录 BOSS）
2. 用户点「连接 Chrome」→ `boss.open` → `connect_over_cdp` → `boss.status: ready`
3. 用户点「抓列表」→ `boss.search` → 在已连接的浏览器中 `goto` 搜索 URL → 解析 → `boss.jobs` + `done`
4. 若像未登录 → `need_login`；用户在 **自己的 Chrome** 里登录后再点「抓列表」

### 并发

同一时刻只允许一个 `boss.search`；重复请求返回 `boss.error`（`code: busy`）。

## 解析与错误

- 导航后等待职位卡片容器出现（默认超时约 20s）
- 选择器集中在 `jobs.py` 常量；站点改版只改该处
- 第一版只抓当前可见列表，不翻页
- 登录墙 / 验证码 → `need_login` 或 `boss.error`，不硬点绕过
- CDP 连不上（没开调试端口 / 端口错）→ `boss.error`，文案说明如何用 `--remote-debugging-port` 启动 Chrome
- 非登录态下解析 0 条 → 仍发 `boss.jobs`（空数组）+ `done`

## 桌面 UI（最小）

- 保留 Ping
- 新增：连接 Chrome、抓列表、状态文案、结果列表（标题 / 公司 / 薪资；链接可打开）
- 仍为现有单页，不新增路由

## 成功标准

- 本机 Chrome 以调试端口运行；Ghostjob 连接后不额外弹出第二套 Chrome profile 窗口
- 在已登录 BOSS 的前提下点「抓列表」，桌面端展示至少一条与搜索页一致的职位信息（有网且页面结构未大变时）
- 退出 Ghostjob 或 `boss.close` 后，用户 Chrome 仍保持运行
