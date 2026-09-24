# ghost-job

Reflex UI + Patchright（本机 Chrome）抓取 BOSS 直聘列表与详情。

## 结构

```text
job/
  __main__.py  # uv run python -m job
  ui/          # Reflex 页面与 State
  lib/boss/    # 抓取会话与解析
```

## 开发

```bash
uv sync
uv run python -m job
```

1. 安装 Google Chrome
2. 浏览器打开 Reflex 页 →「打开 BOSS」→ 在弹出的 Chrome 登录
3. 「抓列表+详情」滚动加载；「停止」结束本卡后退出

Profile：`~/.ghost-job/chrome-profile`
