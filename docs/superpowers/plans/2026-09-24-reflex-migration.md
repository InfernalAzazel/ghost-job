# Reflex 迁移 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除 Electron/Vue 与 FastAPI WebSocket 壳，用 Reflex UI 直接驱动 `BossSession`，并支持滚动加载与停止。

**Architecture:** Reflex `rx.State` 持有单例 `BossSession`；抓取在 `@rx.event(background=True)` 中运行，经 `async with self` 增量更新 `jobs`；`BossSession.search` 支持 `asyncio.Event` 协作取消与滚动翻批。

**Tech Stack:** Python 3.12、Reflex ≥0.9、Patchright、pyquery、pytest。

## Global Constraints

- Spec：`docs/superpowers/specs/2026-09-24-reflex-migration-design.md`
- 删除：`desktop/`、`backend/server.py`、WS 测试、uvicorn/`ghostjob-backend` 入口
- 保留：`backend/boss/jobs.py`、`backend/boss/session.py`、boss 离线单测
- 滚动：最多 20 批；连续 2 次无新增则停；`jobId` 去重
- 停止：本卡结束后退出；终态 `done` | `stopped` | `need_login`
- 长任务必须 `@rx.event(background=True)`，改 State 必须在 `async with self:` 内
- Chrome profile：`~/.ghostjob/chrome-profile`；`channel="chrome"`
- 默认搜索 URL：`backend.boss.jobs.DEFAULT_SEARCH_URL`（勿硬编码第二份）

---

## File Structure

| 文件 | 职责 |
|------|------|
| `backend/boss/jobs.py` | 现有模型；可选增加滚动相关纯函数（去重 key） |
| `backend/boss/session.py` | `request_stop` / `clear_stop`；`search` 滚动循环；每卡/每批回调 |
| `ghostjob/__init__.py` | Reflex 包 |
| `ghostjob/state.py` | `BossState`：open/search/stop/close + background scrape |
| `ghostjob/ghostjob.py` | `rx.App` 页面布局（按钮、列表、日志） |
| `rxconfig.py` | `app_name="ghostjob"` |
| `main.py` | 可选：提示用 `reflex run`，或删除 |
| `pyproject.toml` | 去 fastapi；scripts/描述更新 |
| `README.md` | Reflex 启动说明 |
| `tests/boss/test_session_scroll.py` | 去重/停止条件纯逻辑或 mock 级单测 |
| ~~`desktop/`~~ | 删除 |
| ~~`backend/server.py`~~ | 删除 |
| ~~`tests/boss/test_ws_boss.py`~~ | 删除 |

---

### Task 1: Session 滚动 + 停止（TDD 纯逻辑 + 改造 search）

**Files:**
- Create: `tests/boss/test_session_scroll.py`
- Modify: `backend/boss/session.py`
- Modify: `backend/boss/jobs.py`（仅当需要导出常量 `MAX_SCROLL_BATCHES = 20`）

**Interfaces:**
- Consumes: 现有 `BossSession.search`、`_scrape_cards_with_details`、`Job` / `job_to_dict`
- Produces:
  - `BossSession.request_stop() -> None`
  - `BossSession.clear_stop() -> None`
  - `BossSession.search(url: str | None = None, *, on_job: Callable[[Job], Awaitable[None] | None] | None = None) -> tuple[str, list[Job], str]`
  - 终态：`done` | `stopped` | `need_login`
  - `MAX_SCROLL_BATCHES = 20`（`jobs.py` 或 `session.py` 模块常量）
  - 内部：`_should_stop_scroll(*, stop: bool, empty_streak: int, batch_idx: int) -> bool`

- [ ] **Step 1: 写失败测试（停止/批次条件）**

```python
# tests/boss/test_session_scroll.py
from backend.boss.session import _should_stop_scroll


def test_stop_flag_ends_scroll():
    assert _should_stop_scroll(stop=True, empty_streak=0, batch_idx=0) is True


def test_two_empty_batches_end_scroll():
    assert _should_stop_scroll(stop=False, empty_streak=2, batch_idx=3) is True
    assert _should_stop_scroll(stop=False, empty_streak=1, batch_idx=3) is False


def test_max_batches_end_scroll():
    assert _should_stop_scroll(stop=False, empty_streak=0, batch_idx=20) is True
    assert _should_stop_scroll(stop=False, empty_streak=0, batch_idx=19) is False
```

- [ ] **Step 2: 跑测确认失败**

Run: `uv run pytest tests/boss/test_session_scroll.py -v`  
Expected: FAIL（`_should_stop_scroll` 未定义）

- [ ] **Step 3: 实现 `_should_stop_scroll` + stop Event + search 滚动**

在 `session.py`：

```python
import asyncio
from collections.abc import Awaitable, Callable

MAX_SCROLL_BATCHES = 20


def _should_stop_scroll(*, stop: bool, empty_streak: int, batch_idx: int) -> bool:
    return stop or empty_streak >= 2 or batch_idx >= MAX_SCROLL_BATCHES


class BossSession:
    def __init__(self, user_data_dir: Path | None = None) -> None:
        ...
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        self._stop.set()

    def clear_stop(self) -> None:
        self._stop.clear()

    def _stopped(self) -> bool:
        return self._stop.is_set()
```

改造 `search` 主循环（伪代码，实现时嵌入现有 goto/拦截逻辑）：

```python
async def search(
    self,
    url: str | None = None,
    *,
    on_job: Callable[[Job], Awaitable[None]] | None = None,
) -> tuple[str, list[Job], str]:
    self.clear_stop()
    # ... 现有 goto + joblist 拦截 + login 检测 ...
    all_jobs: list[Job] = []
    seen: set[str] = set()
    empty_streak = 0
    batch_idx = 0
    while not _should_stop_scroll(
        stop=self._stopped(), empty_streak=empty_streak, batch_idx=batch_idx
    ):
        before = await page.locator(CARD_SELECTOR).count()
        # 抓当前 DOM 中尚未 seen 的卡片（按 index；job_id 入 seen）
        new_jobs = await self._scrape_unseen_cards_with_details(
            page,
            salary_by_id=salary_by_id,
            api_items=api_items,
            seen=seen,
            on_job=on_job,
            stop_check=self._stopped,
        )
        all_jobs.extend(new_jobs)
        if self._stopped():
            return page.url, all_jobs, "stopped"
        # 滚动加载
        prev_count = await page.locator(CARD_SELECTOR).count()
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        try:
            async with page.expect_response(
                lambda r: JOBLIST_API_MARKER in r.url and r.status == 200,
                timeout=8_000,
            ):
                pass
        except Exception:
            await page.wait_for_timeout(1_500)
        after = await page.locator(CARD_SELECTOR).count()
        if after <= prev_count and not new_jobs:
            empty_streak += 1
        else:
            empty_streak = 0
        batch_idx += 1
    state = "stopped" if self._stopped() else "done"
    return page.url, all_jobs, state
```

将现有 `_scrape_cards_with_details` 改为或新增 `_scrape_unseen_cards_with_details`：跳过 `job_id in seen`；每完成一张 `seen.add(job_id)`；若 `stop_check()` 则提前返回已抓列表；若提供 `on_job` 则 `await on_job(job)`。

首批：`api_items` 在滚动后应 **append/合并** 新 `joblist.json`（`salary_by_id.update`；`api_items` 按 encryptJobId 去重追加，勿 `clear()` 掉旧项——或按 DOM 索引对齐时只用 salary map）。推荐：**salary_by_id 持续 update；列表字段优先 DOM + salary map，list HR 用 api_items 按 job_id 查找**。

增加 helper：

```python
def api_item_by_job_id(items: list[dict], job_id: str | None) -> dict | None:
    if not job_id:
        return None
    for it in items:
        if str(it.get("encryptJobId") or "") == job_id:
            return it
    return None
```

- [ ] **Step 4: 跑测通过**

Run: `uv run pytest tests/boss/test_session_scroll.py tests/boss/test_jobs_parse.py tests/boss/test_session_unit.py -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/boss/session.py backend/boss/jobs.py tests/boss/test_session_scroll.py
git commit -m "$(cat <<'EOF'
feat(boss): scroll load more jobs with cooperative stop

EOF
)"
```

---

### Task 2: 脚手架 Reflex 应用（可打开空页）

**Files:**
- Create: `rxconfig.py`
- Create: `ghostjob/__init__.py`
- Create: `ghostjob/state.py`（最小 State）
- Create: `ghostjob/ghostjob.py`
- Modify: `pyproject.toml`（确认 `reflex` 依赖；更新 description）
- Modify: `README.md`（启动命令改为 `uv run reflex run`）

**Interfaces:**
- Produces: `rxconfig.app_name == "ghostjob"`；`ghostjob.ghostjob.app`；`BossState` 可实例化

- [ ] **Step 1: 写 `rxconfig.py`**

```python
import reflex as rx

config = rx.Config(
    app_name="ghostjob",
)
```

- [ ] **Step 2: 最小 State + 页面**

`ghostjob/__init__.py`：空文件或 docstring。

`ghostjob/state.py`：

```python
import reflex as rx


class BossState(rx.State):
    boss_state: str = "—"
    busy: bool = False
    log: list[str] = []
    jobs: list[dict] = []

    def _push_log(self, line: str) -> None:
        self.log = [line, *self.log][:20]
```

`ghostjob/ghostjob.py`：

```python
import reflex as rx

from ghostjob.state import BossState


def index() -> rx.Component:
    return rx.container(
        rx.heading("Ghostjob", size="8"),
        rx.text(f"状态：{BossState.boss_state}"),
        rx.text("Reflex 壳就绪"),
        padding="2em",
        max_width="720px",
    )


app = rx.App()
app.add_page(index, route="/", title="Ghostjob")
```

注意：Reflex 模板字符串绑定用 `BossState.boss_state` 而非 f-string；上面 `rx.text` 应写为：

```python
rx.text(BossState.boss_state)
```

- [ ] **Step 3: 同步依赖并初始化**

```bash
cd /Users/kylin/work/code/github/ghostjob
uv sync
uv run reflex init --help >/dev/null  # 若已有 rxconfig 可跳过 init
uv run reflex run --backend-port 8000
```

Expected: 浏览器打开后看到 “Ghostjob” 标题；Ctrl+C 停。

若 `reflex run` 需要先 `reflex init` 生成 `.web`，在已有 `rxconfig.py` 时直接 `reflex run` 即可。

- [ ] **Step 4: Commit**

```bash
git add rxconfig.py ghostjob/ pyproject.toml README.md
git commit -m "$(cat <<'EOF'
feat: scaffold Reflex app shell

EOF
)"
```

---

### Task 3: State 接入 BossSession（open / close / search / stop）

**Files:**
- Modify: `ghostjob/state.py`
- Modify: `ghostjob/ghostjob.py`（按钮与列表）
- Test: 手动；可选轻量单测不强制（Reflex State 难在无浏览器下测）

**Interfaces:**
- Consumes: `BossSession.request_stop/clear_stop/open/close/search`；`job_to_dict`；`DEFAULT_SEARCH_URL`
- Produces: UI 事件 `open_boss`、`start_search`（background）、`stop_search`、`close_boss`

- [ ] **Step 1: 实现 `BossState` 完整逻辑**

```python
from __future__ import annotations

import reflex as rx

from backend.boss.jobs import DEFAULT_SEARCH_URL, job_to_dict
from backend.boss.session import BossSession

_session = BossSession()


class BossState(rx.State):
    boss_state: str = "—"
    busy: bool = False
    log: list[str] = []
    jobs: list[dict] = []

    def _push_log(self, line: str) -> None:
        self.log = [line, *self.log][:20]

    @rx.event
    async def open_boss(self):
        if self.busy:
            return
        self.busy = True
        self.boss_state = "launching"
        self._push_log("→ open")
        try:
            await _session.open()
            self.boss_state = "ready"
            self._push_log("Chrome ready")
        except Exception as exc:  # noqa: BLE001
            self.boss_state = f"error: {exc}"
            self._push_log(str(exc))
        finally:
            self.busy = False

    @rx.event
    def stop_search(self):
        _session.request_stop()
        self._push_log("→ stop")
        self.boss_state = "stopping"

    @rx.event
    async def close_boss(self):
        await _session.close()
        self.boss_state = "done"
        self.busy = False
        self._push_log("→ close")

    @rx.event(background=True)
    async def start_search(self):
        async with self:
            if self.busy:
                return
            self.busy = True
            self.boss_state = "navigating"
            self.jobs = []
            self._push_log("→ search")

        async def on_job(job) -> None:
            async with self:
                self.jobs = [*self.jobs, job_to_dict(job)]
                self.boss_state = "scraping"

        try:
            if not _session.is_open:
                await _session.open()
            final_url, _jobs, state = await _session.search(
                DEFAULT_SEARCH_URL, on_job=on_job
            )
            async with self:
                self.boss_state = state
                self._push_log(f"search {state} url={final_url} n={len(self.jobs)}")
                self.busy = False
        except Exception as exc:  # noqa: BLE001
            async with self:
                self.boss_state = f"error: {exc}"
                self._push_log(str(exc))
                self.busy = False
```

- [ ] **Step 2: 页面绑定按钮与列表**

`ghostjob/ghostjob.py` 中：

```python
def index() -> rx.Component:
    return rx.container(
        rx.heading("Ghostjob", size="8"),
        rx.hstack(
            rx.button("打开 BOSS", on_click=BossState.open_boss, disabled=BossState.busy),
            rx.button(
                "抓列表+详情",
                on_click=BossState.start_search,
                disabled=BossState.busy,
                color_scheme="green",
            ),
            rx.button(
                "停止",
                on_click=BossState.stop_search,
                disabled=~BossState.busy,
                color_scheme="red",
            ),
            rx.button("关闭", on_click=BossState.close_boss),
            spacing="3",
        ),
        rx.text(BossState.boss_state),
        rx.foreach(
            BossState.jobs,
            lambda job: rx.box(
                rx.link(job["title"], href=job["link"], is_external=True),
                rx.text(
                    job["salary"]
                    + " · "
                    + job["company"]
                    + " · "
                    + job["location"]
                ),
                rx.cond(
                    job["hrName"] != "",
                    rx.text("HR：" + job["hrName"] + " · " + job["hrTitle"]),
                ),
                rx.cond(job["address"] != "", rx.text("地址：" + job["address"])),
                rx.cond(
                    job["description"] != "",
                    rx.text(job["description"], white_space="pre-wrap"),
                ),
                border_bottom="1px solid #333",
                padding_y="0.75em",
                width="100%",
            ),
        ),
        rx.heading("日志", size="4", margin_top="1.5em"),
        rx.foreach(BossState.log, lambda line: rx.text(line, font_size="0.85em")),
        padding="2em",
        max_width="720px",
    )
```

若 Reflex `rx.foreach` 对 `dict` 键访问语法不同，改用 `TypedDict`/`rx.Base` 模型字段（`JobRow`），计划允许实现时微调绑定语法，但字段名必须与 `job_to_dict` 的 alias 一致：`title/salary/company/location/experience/education/link/jobId/description/hrName/hrTitle/address`。

- [ ] **Step 3: 手动验收**

```bash
uv run reflex run
```

1. 打开 BOSS → Chrome 起、状态 `ready`  
2. 抓列表+详情 → 列表增量出现；终端有 `print_job`  
3. 滚动持续加载；点停止 → 状态 `stopped`，已抓结果保留  
4. 关闭 → Chrome 关

- [ ] **Step 4: Commit**

```bash
git add ghostjob/
git commit -m "$(cat <<'EOF'
feat: wire Reflex UI to BossSession with stop

EOF
)"
```

---

### Task 4: 拆除 Electron / FastAPI 壳

**Files:**
- Delete: `desktop/`（整个目录）
- Delete: `backend/server.py`
- Delete: `tests/boss/test_ws_boss.py`
- Modify or Delete: `main.py`
- Modify: `pyproject.toml`（移除 `fastapi[standard]`；移除 `ghostjob-backend` script 或改为文档说明）
- Modify: `README.md`（架构图改为 Reflex）

**Interfaces:**
- Consumes: Task 2–3 已可独立运行
- Produces: 仓库无 Electron/FastAPI 运行路径

- [ ] **Step 1: 删除壳与 WS 测试**

```bash
cd /Users/kylin/work/code/github/ghostjob
rm -rf desktop
rm -f backend/server.py tests/boss/test_ws_boss.py
```

`main.py` 改为：

```python
"""Use: uv run reflex run"""

raise SystemExit("Use `uv run reflex run` to start Ghostjob.")
```

或直接删除 `main.py`（若删除，README 勿再引用）。

- [ ] **Step 2: 更新 `pyproject.toml`**

```toml
[project]
name = "ghostjob"
version = "0.1.0"
description = "Ghostjob — Reflex UI + Patchright BOSS scraper"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "patchright>=1.63.0",
    "pyquery>=2.1.0",
    "reflex>=0.9.12",
]

# 删除 [project.scripts] ghostjob-backend，或留空
```

```bash
uv lock
uv sync
```

- [ ] **Step 3: README**

```markdown
# ghostjob

Reflex UI + Patchright（本机 Chrome）抓取 BOSS 直聘列表与详情。

## 开发

```bash
uv sync
uv run reflex run
```

1. 安装 Google Chrome
2. 浏览器打开 Reflex 页 →「打开 BOSS」→ 在弹出的 Chrome 登录
3. 「抓列表+详情」滚动加载；「停止」结束本卡后退出

Profile：`~/.ghostjob/chrome-profile`
```

- [ ] **Step 4: 全量测试**

```bash
uv run pytest tests/boss/ -q
```

Expected: 全部 PASS；无 fastapi/ws 导入错误。

- [ ] **Step 5: Commit**

```bash
git add -A
git status   # 确认 desktop/、server.py、test_ws_boss.py 已删
git commit -m "$(cat <<'EOF'
chore: remove Electron and FastAPI WebSocket shell

EOF
)"
```

---

### Task 5: Spec/文档对齐 + 冒烟

**Files:**
- Modify: `docs/superpowers/specs/2026-09-24-boss-job-detail-design.md`（非目标里「不翻页」改为指向滚动 spec）
- 可选：在 `2026-09-24-reflex-migration-design.md` 末尾加「已实现」无勾（不强制）

- [ ] **Step 1: 更新详情 design 的非目标**

将「不翻页」改为：「传统分页控件不做；滚动加载见 Reflex 迁移 spec」。

- [ ] **Step 2: 冒烟清单**

- [ ] `uv run reflex run` 启动成功  
- [ ] open → search → 增量 jobs → stop → close  
- [ ] `pytest tests/boss/` 绿  

- [ ] **Step 3: Commit（若有文档改动）**

```bash
git add docs/superpowers/specs/
git commit -m "$(cat <<'EOF'
docs: align boss detail spec with scroll loading

EOF
)"
```

---

## Spec coverage（自检）

| Spec 要求 | Task |
|-----------|------|
| 删 Electron/`desktop/` | Task 4 |
| 删 FastAPI/`server.py`/WS | Task 4 |
| Reflex State 直调 BossSession | Task 3 |
| 打开/抓取/停止/关闭按钮 | Task 3 |
| 列表字段含 HR/地址/描述 | Task 3（`job_to_dict`） |
| 滚动 + jobId 去重 + 20 批 + 双空停 | Task 1 |
| background 事件 | Task 3 |
| README / 依赖清理 | Task 2 + 4 |
| 保留 boss 单测、删 WS 测 | Task 1 + 4 |

## Placeholder scan

无 TBD；`rx.foreach` dict 绑定允许实现微调，字段名已钉死。
