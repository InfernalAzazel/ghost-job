# BOSS 直聘列表接入（Patchright + Chrome persistent）

## 目标

第一版用 **Patchright** `launch_persistent_context(channel="chrome")` 拉起本机 Google Chrome（独立 profile），打开 BOSS 搜索页，抓取职位列表，经现有 WebSocket 推到 Electron/Vue 桌面端展示。

默认搜索 URL：

`https://www.zhipin.com/web/geek/jobs?city=101280100&jobType=1901&query=ai应用开发`

## 非目标（v1）

- 职位详情、立即沟通、投递
- 翻页、多账号、无头模式
- 自动轮询登录 / 绕过验证码
- CDP 附着用户日常 Chrome（需 `--remote-debugging-port`）
- Electron 内嵌 BOSS 页面做自动化

## 架构

```text
Vue  --WS /ws-->  FastAPI gateway  --owns-->  BossSession (Patchright)
                                           |
                                           v
                                Chrome (channel=chrome)
                                user_data_dir=~/.ghostjob/chrome-profile
```

## 浏览器约束

```python
context = await playwright.chromium.launch_persistent_context(
    user_data_dir="~/.ghostjob/chrome-profile",  # 实现时展开为绝对路径
    channel="chrome",
    headless=False,
    no_viewport=True,
    # 不设置自定义 user_agent / extra_http_headers
)
```

- 仅使用本机 **Chrome**
- 登录态落在独立 profile，跨次保留
- `boss.close` / 应用退出：关闭该自动化 Chrome；**保留** profile 目录

## WebSocket / UI

- `boss.open` → 拉起 Chrome → `ready`
- `boss.search` → 导航默认搜索 URL → `boss.jobs`
- 桌面按钮：「打开 BOSS」「抓列表」

其余协议字段与并发 busy 锁与实现保持一致（见 `backend/server.py`）。
