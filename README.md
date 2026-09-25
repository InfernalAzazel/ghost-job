# ghost-job

Reflex UI + Patchright（本机 Chrome）抓取 BOSS 直聘列表与详情。

## 结构

```text
job/
  __main__.py
  ui/             # Reflex 页面
  boss/           # BOSS 抓取
  models/         # 表定义 + 引擎 + CRUD
```

## 开发

按 [reflex-desktop](https://github.com/FarhanAliRaza/reflex-desktop) 文档，日常迭代用 **`reflex-desktop dev`**（原生窗口 + 热重载）：

```bash
uv sync
# 前置：较新的 Rust（建议 rustup 稳定版 ≥1.85）、Xcode CLT、Tauri CLI
cargo install tauri-cli --locked   # 仅首次 / doctor --bundle 提示时
uv run reflex-desktop doctor --bundle
uv run python -m job               # 等价于 reflex-desktop dev
# 仅浏览器调试：uv run reflex run
```

1. 安装 Google Chrome
2. 桌面窗口打开后 →「打开 BOSS」→ 在弹出的 Chrome 登录
3. 「抓列表+详情」滚动加载；「停止」结束本卡后退出

Profile：`~/.ghost-job/chrome-profile`  
SQLite：`~/.ghost-job/ghost-job.db`
