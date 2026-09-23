# BOSS Patchright Jobs List Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 Patchright `connect_over_cdp` 附着本机已开调试端口的 Chrome，打开 BOSS 搜索页，抓职位列表，经现有 `/ws` 推到 Vue 桌面端展示。

**Architecture:** FastAPI 网关持有单例 `BossSession`；`jobs.py` 只负责选择器与字段抽取；Vue 发 `boss.open` / `boss.search`，收 `boss.status` / `boss.jobs` / `boss.error`。连接 CDP，不另起 Chrome。

**Tech Stack:** Python 3.12、Patchright、FastAPI WebSocket、Vue 3、pytest。

## Global Constraints

- 浏览器：Patchright `chromium.connect_over_cdp`，默认 `http://127.0.0.1:9222`（`GHOSTJOB_CDP_URL` 可覆盖）
- 禁止 `launch_persistent_context` / 独立 `user_data_dir`；禁止自定义 `user_agent` / `extra_http_headers`
- `boss.close` / 进程退出只断开 CDP，不杀掉用户 Chrome
- 默认搜索 URL：`https://www.zhipin.com/web/geek/jobs?city=101280100&jobType=1901&query=ai应用开发`
- v1 不做：详情、投递、翻页、无头、自动登录轮询、Electron 内嵌 BOSS
- Spec：`docs/superpowers/specs/2026-09-23-boss-patchright-jobs-design.md`

---

## File Structure

| 文件 | 职责 |
|------|------|
| `backend/boss/__init__.py` | 包导出 |
| `backend/boss/jobs.py` | `Job` 模型、选择器常量、HTML/Page 抽取、登录墙检测 |
| `backend/boss/session.py` | `BossSession`：CDP 连接/断开、导航、调用抽取 |
| `backend/server.py` | WS 路由、busy 锁、lifespan 关 session |
| `tests/boss/fixtures/job_list_snippet.html` | 离线 HTML 夹具 |
| `tests/boss/test_jobs_parse.py` | 解析与登录检测单测 |
| `tests/boss/test_ws_boss.py` | WS 协议（mock session） |
| `desktop/src/App.vue` | 打开 BOSS / 抓列表 / 状态 / 结果列表 |
| `pyproject.toml` | 增加 pytest 开发依赖 |

---

### Task 1: Job 解析（离线 TDD）

**Files:**
- Create: `backend/boss/__init__.py`
- Create: `backend/boss/jobs.py`
- Create: `tests/boss/fixtures/job_list_snippet.html`
- Create: `tests/boss/test_jobs_parse.py`
- Modify: `pyproject.toml`（dev 依赖 pytest）

**Interfaces:**
- Produces:
  - `Job` dataclass：`title: str`, `company: str`, `salary: str`, `link: str`, `job_id: str | None`
  - `DEFAULT_SEARCH_URL: str`
  - `CARD_SELECTOR`, `LOGIN_HINT_SELECTOR` 等常量
  - `parse_jobs_from_html(html: str) -> list[Job]`
  - `looks_like_login_wall(html: str, url: str = "") -> bool`
  - `job_to_dict(job: Job) -> dict[str, str | None]`（WS 用 camelCase `jobId`）

- [ ] **Step 1: 添加 pytest 并写失败测试**

```bash
cd /Users/kylin/work/code/github/ghostjob
uv add --dev pytest
```

创建 `tests/boss/fixtures/job_list_snippet.html`：

```html
<!DOCTYPE html>
<html>
  <body>
    <div class="job-list-box">
      <li class="job-card-box" data-jobid="10001">
        <a class="job-card-left" href="/job_detail/10001.html">
          <span class="job-name">AI应用开发工程师</span>
          <span class="salary">25-40K</span>
        </a>
        <span class="boss-name">某科技有限公司</span>
      </li>
      <li class="job-card-box" data-jobid="10002">
        <a class="job-card-left" href="https://www.zhipin.com/job_detail/10002.html">
          <span class="job-name">AI Agent 工程师</span>
          <span class="salary">30-50K·15薪</span>
        </a>
        <span class="boss-name">另一家公司</span>
      </li>
    </div>
    <div class="login-dialog-wrap" style="display:none"></div>
  </body>
</html>
```

创建 `tests/boss/test_jobs_parse.py`：

```python
from pathlib import Path

from backend.boss.jobs import (
    job_to_dict,
    looks_like_login_wall,
    parse_jobs_from_html,
)

FIXTURE = Path(__file__).parent / "fixtures" / "job_list_snippet.html"


def test_parse_jobs_from_html_extracts_fields():
    html = FIXTURE.read_text(encoding="utf-8")
    jobs = parse_jobs_from_html(html)
    assert len(jobs) == 2
    assert jobs[0].title == "AI应用开发工程师"
    assert jobs[0].company == "某科技有限公司"
    assert jobs[0].salary == "25-40K"
    assert jobs[0].job_id == "10001"
    assert jobs[0].link.endswith("/job_detail/10001.html")
    assert jobs[1].title == "AI Agent 工程师"


def test_job_to_dict_uses_jobId():
    html = FIXTURE.read_text(encoding="utf-8")
    d = job_to_dict(parse_jobs_from_html(html)[0])
    assert d["jobId"] == "10001"
    assert "title" in d and "company" in d and "salary" in d and "link" in d


def test_looks_like_login_wall_when_dialog_visible():
    html = '<div class="login-dialog-wrap"></div><div class="job-list-box"></div>'
    assert looks_like_login_wall(html) is True


def test_looks_like_login_wall_false_when_jobs_present():
    html = FIXTURE.read_text(encoding="utf-8")
    assert looks_like_login_wall(html) is False
```

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest tests/boss/test_jobs_parse.py -v
```

Expected: FAIL（`ModuleNotFoundError: backend.boss` 或类似）

- [ ] **Step 3: 实现 `backend/boss/jobs.py` 与包初始化**

`backend/boss/__init__.py`：

```python
"""BOSS Zhipin browser automation helpers."""
```

`backend/boss/jobs.py`：

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin

DEFAULT_SEARCH_URL = (
    "https://www.zhipin.com/web/geek/jobs"
    "?city=101280100&jobType=1901&query=ai应用开发"
)
BASE_URL = "https://www.zhipin.com"

# 选择器集中在此；站点改版只改这里。
CARD_SELECTOR = "li.job-card-box"
TITLE_SELECTOR = ".job-name"
SALARY_SELECTOR = ".salary"
COMPANY_SELECTOR = ".boss-name"
LINK_SELECTOR = "a.job-card-left"
LOGIN_HINT_SELECTOR = ".login-dialog-wrap"
JOB_LIST_HINT = ".job-list-box"


@dataclass(frozen=True)
class Job:
    title: str
    company: str
    salary: str
    link: str
    job_id: str | None = None


def job_to_dict(job: Job) -> dict[str, str | None]:
    return {
        "title": job.title,
        "company": job.company,
        "salary": job.salary,
        "link": job.link,
        "jobId": job.job_id,
    }


class _JobListParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.jobs: list[Job] = []
        self._in_card = False
        self._card_job_id: str | None = None
        self._href: str | None = None
        self._capture: str | None = None
        self._buf: list[str] = []
        self._title = ""
        self._salary = ""
        self._company = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = {k: (v or "") for k, v in attrs}
        cls = ad.get("class", "")
        if tag == "li" and "job-card-box" in cls.split():
            self._in_card = True
            self._card_job_id = ad.get("data-jobid") or None
            self._href = None
            self._title = self._salary = self._company = ""
        if not self._in_card:
            return
        if tag == "a" and "job-card-left" in cls.split():
            self._href = ad.get("href") or None
        if tag == "span" and "job-name" in cls.split():
            self._capture = "title"
            self._buf = []
        elif tag == "span" and "salary" in cls.split():
            self._capture = "salary"
            self._buf = []
        elif tag == "span" and "boss-name" in cls.split():
            self._capture = "company"
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if self._capture and tag == "span":
            text = "".join(self._buf).strip()
            if self._capture == "title":
                self._title = text
            elif self._capture == "salary":
                self._salary = text
            elif self._capture == "company":
                self._company = text
            self._capture = None
            self._buf = []
        if tag == "li" and self._in_card:
            link = urljoin(BASE_URL, self._href or "")
            if self._title:
                self.jobs.append(
                    Job(
                        title=self._title,
                        company=self._company,
                        salary=self._salary,
                        link=link,
                        job_id=self._card_job_id,
                    )
                )
            self._in_card = False

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buf.append(data)


def parse_jobs_from_html(html: str) -> list[Job]:
    parser = _JobListParser()
    parser.feed(html)
    return parser.jobs


def looks_like_login_wall(html: str, url: str = "") -> bool:
    """True when page looks like a login wall rather than a job list."""
    del url
    if parse_jobs_from_html(html):
        return False
    if not re.search(r"login-dialog-wrap", html):
        return False
    if re.search(r'login-dialog-wrap[^>]*style="[^"]*display:\s*none', html, re.I):
        return False
    return True
```

- [ ] **Step 4: 跑测试确认通过**

```bash
uv run pytest tests/boss/test_jobs_parse.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock backend/boss tests/boss
git commit -m "$(cat <<'EOF'
feat: add BOSS job list HTML parser

Offline-parse job cards so list extraction can be tested without Chrome.
EOF
)"
```

---

### Task 2: BossSession（Patchright CDP 附着）

**Files:**
- Create: `backend/boss/session.py`
- Create: `tests/boss/test_session_unit.py`

**Interfaces:**
- Consumes: `parse_jobs_from_html`, `looks_like_login_wall`, `DEFAULT_SEARCH_URL`, `Job` from `backend.boss.jobs`
- Produces:
  - `DEFAULT_CDP_URL: str`（`"http://127.0.0.1:9222"`）
  - `def resolve_cdp_url() -> str`（读 `GHOSTJOB_CDP_URL`）
  - `class BossSession`
  - `async def open(self) -> None` — `connect_over_cdp`
  - `async def close(self) -> None` — 断开连接，不杀 Chrome
  - `async def search(self, url: str | None = None) -> tuple[str, list[Job], str]`  
    返回 `(final_url, jobs, state)`，`state` 为 `"done"` | `"need_login"`
  - `property is_open: bool`

- [ ] **Step 1: 写 CDP URL 解析单元测试（不连 Chrome）**

`tests/boss/test_session_unit.py`：

```python
from backend.boss.session import DEFAULT_CDP_URL, resolve_cdp_url


def test_resolve_cdp_url_default(monkeypatch):
    monkeypatch.delenv("GHOSTJOB_CDP_URL", raising=False)
    assert resolve_cdp_url() == DEFAULT_CDP_URL


def test_resolve_cdp_url_from_env(monkeypatch):
    monkeypatch.setenv("GHOSTJOB_CDP_URL", "http://127.0.0.1:9333")
    assert resolve_cdp_url() == "http://127.0.0.1:9333"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest tests/boss/test_session_unit.py -v
```

Expected: FAIL（`resolve_cdp_url` 未定义）

- [ ] **Step 3: 实现 `backend/boss/session.py`**

```python
from __future__ import annotations

import os

from patchright.async_api import Browser, Page, async_playwright

from backend.boss.jobs import (
    CARD_SELECTOR,
    DEFAULT_SEARCH_URL,
    Job,
    looks_like_login_wall,
    parse_jobs_from_html,
)

DEFAULT_CDP_URL = "http://127.0.0.1:9222"

_CDP_HINT = (
    "无法连接 Chrome CDP。请先完全退出 Chrome，再用调试端口启动，例如：\n"
    '/Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222'
)


def resolve_cdp_url() -> str:
    return os.environ.get("GHOSTJOB_CDP_URL", DEFAULT_CDP_URL)


class BossSession:
    def __init__(self, cdp_url: str | None = None) -> None:
        self.cdp_url = cdp_url or resolve_cdp_url()
        self._playwright = None
        self._browser: Browser | None = None

    @property
    def is_open(self) -> bool:
        return self._browser is not None

    async def open(self) -> None:
        if self._browser is not None:
            return
        self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(self.cdp_url)
        except Exception as exc:  # noqa: BLE001
            await self.close()
            raise RuntimeError(f"{_CDP_HINT}\n当前 CDP：{self.cdp_url}\n原因：{exc}") from exc

    async def close(self) -> None:
        # 只断开 CDP，不关闭用户 Chrome
        self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:  # noqa: BLE001
                pass
            self._playwright = None

    async def _page(self) -> Page:
        if self._browser is None:
            raise RuntimeError("BossSession 未连接，请先 boss.open")
        contexts = self._browser.contexts
        if not contexts:
            raise RuntimeError("CDP 已连接但没有 browser context")
        context = contexts[0]
        if context.pages:
            return context.pages[0]
        return await context.new_page()

    async def search(self, url: str | None = None) -> tuple[str, list[Job], str]:
        if self._browser is None:
            await self.open()
        target = url or DEFAULT_SEARCH_URL
        page = await self._page()
        await page.goto(target, wait_until="domcontentloaded")
        try:
            await page.wait_for_selector(CARD_SELECTOR, timeout=20_000)
        except Exception:  # noqa: BLE001
            html = await page.content()
            final = page.url
            if looks_like_login_wall(html, final):
                return final, [], "need_login"
            return final, parse_jobs_from_html(html), "done"
        html = await page.content()
        final = page.url
        if looks_like_login_wall(html, final):
            return final, [], "need_login"
        return final, parse_jobs_from_html(html), "done"
```

- [ ] **Step 4: 跑单元测试**

```bash
uv run pytest tests/boss/test_session_unit.py tests/boss/test_jobs_parse.py -v
```

Expected: PASS

- [ ] **Step 5: 手动冒烟（需本机 Chrome 已开调试端口）**

```bash
# 先退出所有 Chrome，再：
# /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222

uv run python - <<'PY'
import asyncio
from backend.boss.session import BossSession

async def main():
    s = BossSession()
    await s.open()
    print("cdp ok", s.cdp_url)
    url, jobs, state = await s.search()
    print(state, url, len(jobs))
    if jobs:
        print(jobs[0])
    await s.close()

asyncio.run(main())
PY
```

Expected: **不**新开独立 profile 窗口；在已有 Chrome 里导航；未登录时 `need_login` 或空列表；登录后 `done` 且 `len(jobs) > 0`（DOM 与夹具不一致时允许在本 Task 修正选择器）。

- [ ] **Step 6: Commit**

```bash
git add backend/boss/session.py tests/boss/test_session_unit.py backend/boss/jobs.py tests/boss/fixtures
git commit -m "$(cat <<'EOF'
feat: add BossSession via Patchright CDP attach

Connect to the user's running Chrome instead of launching a new profile.
EOF
)"
```

---

### Task 3: WebSocket 协议接入

**Files:**
- Modify: `backend/server.py`
- Create: `tests/boss/test_ws_boss.py`

**Interfaces:**
- Consumes: `BossSession`, `DEFAULT_SEARCH_URL`, `job_to_dict`
- Produces: WS 处理 `boss.open` / `boss.search` / `boss.close`；推送 `boss.status` / `boss.jobs` / `boss.error`

- [ ] **Step 1: 写 WS 协议测试（mock BossSession）**

`tests/boss/test_ws_boss.py`：

```python
import pytest
from fastapi.testclient import TestClient

from backend import server
from backend.boss.jobs import Job


class FakeSession:
    def __init__(self) -> None:
        self.is_open = False
        self.closed = False

    async def open(self) -> None:
        self.is_open = True

    async def close(self) -> None:
        self.closed = True
        self.is_open = False

    async def search(self, url: str | None = None):
        return (
            url or "https://example.test/jobs",
            [Job("T", "C", "10K", "https://example.test/j/1", "1")],
            "done",
        )


@pytest.fixture()
def client(monkeypatch):
    fake = FakeSession()
    monkeypatch.setattr(server, "boss_session", fake)
    monkeypatch.setattr(server, "_search_lock", __import__("asyncio").Lock())
    with TestClient(server.app) as c:
        yield c, fake


def test_boss_open_and_search(client):
    c, fake = client
    with c.websocket_connect("/ws") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        ws.send_json({"type": "boss.open"})
        status = ws.receive_json()
        assert status["type"] == "boss.status"
        assert status["state"] == "ready"
        assert fake.is_open is True
        ws.send_json({"type": "boss.search"})
        # may receive navigating then jobs/done
        msgs = [ws.receive_json(), ws.receive_json(), ws.receive_json()]
        types = {m["type"] for m in msgs}
        assert "boss.jobs" in types
        jobs_msg = next(m for m in msgs if m["type"] == "boss.jobs")
        assert jobs_msg["jobs"][0]["title"] == "T"
```

若消息顺序严格为 `navigating` → `boss.jobs` → `done`，把断言改成按序读取三次。

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest tests/boss/test_ws_boss.py -v
```

Expected: FAIL（无 `boss.open` 处理）

- [ ] **Step 3: 改造 `backend/server.py`**

在文件顶部增加导入与全局状态；用 lifespan 关闭 session；在 websocket 循环里分支处理 boss 消息。关键片段：

```python
import asyncio
from contextlib import asynccontextmanager

from backend.boss.jobs import DEFAULT_SEARCH_URL, job_to_dict
from backend.boss.session import BossSession

boss_session = BossSession()
_search_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await boss_session.close()


app = FastAPI(title="ghostjob-backend", version="0.1.0", lifespan=lifespan)
# ... CORS 保持不变 ...


async def _handle_boss(websocket: WebSocket, payload: dict) -> None:
    typ = payload.get("type")
    if typ == "boss.open":
        await websocket.send_json({"type": "boss.status", "state": "launching"})
        try:
            await boss_session.open()
            await websocket.send_json({"type": "boss.status", "state": "ready"})
        except Exception as exc:  # noqa: BLE001
            await websocket.send_json(
                {"type": "boss.error", "message": str(exc), "code": "launch_failed"}
            )
            await websocket.send_json(
                {"type": "boss.status", "state": "error", "message": str(exc)}
            )
        return

    if typ == "boss.close":
        await boss_session.close()
        await websocket.send_json({"type": "boss.status", "state": "done", "message": "closed"})
        return

    if typ == "boss.search":
        if _search_lock.locked():
            await websocket.send_json(
                {"type": "boss.error", "message": "search already running", "code": "busy"}
            )
            return
        async with _search_lock:
            await websocket.send_json({"type": "boss.status", "state": "navigating"})
            try:
                url = payload.get("url") or DEFAULT_SEARCH_URL
                final_url, jobs, state = await boss_session.search(url)
                await websocket.send_json(
                    {
                        "type": "boss.jobs",
                        "url": final_url,
                        "jobs": [job_to_dict(j) for j in jobs],
                    }
                )
                await websocket.send_json({"type": "boss.status", "state": state})
            except Exception as exc:  # noqa: BLE001
                await websocket.send_json(
                    {"type": "boss.error", "message": str(exc), "code": "search_failed"}
                )
                await websocket.send_json(
                    {"type": "boss.status", "state": "error", "message": str(exc)}
                )
        return
```

在 `websocket_endpoint` 的 `ping` 分支之后、`else` echo 之前调用：

```python
if str(payload.get("type", "")).startswith("boss."):
    await _handle_boss(websocket, payload)
    continue
```

保留 `ping` / `pong` / `hello` / `echo`。

- [ ] **Step 4: 跑测试**

```bash
uv run pytest tests/boss -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/server.py tests/boss/test_ws_boss.py
git commit -m "$(cat <<'EOF'
feat: wire boss.open/search/close over WebSocket

Expose Patchright session through the existing /ws gateway.
EOF
)"
```

---

### Task 4: Vue 桌面端最小 UI

**Files:**
- Modify: `desktop/src/App.vue`

**Interfaces:**
- Consumes: WS 消息 `boss.status` / `boss.jobs` / `boss.error`
- Produces: 按钮「连接 Chrome」「抓列表」；状态文案；职位列表

- [ ] **Step 1: 扩展 `App.vue` 状态与发送函数**

在 `<script setup>` 中增加：

```ts
type BossJob = {
  title: string
  company: string
  salary: string
  link: string
  jobId?: string | null
}

const bossState = ref('—')
const bossJobs = ref<BossJob[]>([])
const bossBusy = ref(false)

function sendBoss(type: 'boss.open' | 'boss.search' | 'boss.close') {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    pushLog(`${type} skipped: not connected`)
    return
  }
  const payload = JSON.stringify({ type })
  socket.send(payload)
  pushLog(`→ ${payload}`)
}

// 在 socket.onmessage 的 JSON 分支中追加：
if (data.type === 'boss.status') {
  bossState.value = data.state || ''
  if (data.state === 'navigating') bossBusy.value = true
  if (data.state === 'done' || data.state === 'need_login' || data.state === 'error' || data.state === 'ready') {
    bossBusy.value = false
  }
}
if (data.type === 'boss.jobs' && Array.isArray(data.jobs)) {
  bossJobs.value = data.jobs as BossJob[]
}
if (data.type === 'boss.error') {
  bossState.value = `error: ${data.message || ''}`
  bossBusy.value = false
}
```

（按现有 `onmessage` 结构合并类型，避免 TS 报错。）

- [ ] **Step 2: 模板增加 BOSS 区块**

在 Ping 的 `section.panel` 之后插入：

```vue
    <section class="panel">
      <h2>BOSS</h2>
      <div class="row">
        <span class="label">状态</span>
        <span class="value">{{ bossState }}</span>
      </div>
      <div class="actions">
        <button type="button" :disabled="status !== 'connected' || bossBusy" @click="sendBoss('boss.open')">
          连接 Chrome
        </button>
        <button type="button" :disabled="status !== 'connected' || bossBusy" @click="sendBoss('boss.search')">
          抓列表
        </button>
      </div>
      <ul class="jobs" v-if="bossJobs.length">
        <li v-for="(job, i) in bossJobs" :key="job.jobId || i">
          <a :href="job.link" target="_blank" rel="noreferrer">{{ job.title }}</a>
          <span class="meta">{{ job.company }} · {{ job.salary }}</span>
        </li>
      </ul>
    </section>
```

补充少量 scoped CSS（`.jobs`、`.meta`、`h2`），保持与现有 panel 风格一致。

- [ ] **Step 3: 手动验证**

```bash
# 终端 1：仓库根
uv run python main.py

# 终端 2
cd desktop && npm run dev
```

操作：窗口显示已连接 → 连接 Chrome（Chrome 须已开调试端口）→（如需）在 Chrome 扫码登录 → 抓列表 → 看到职位行。

- [ ] **Step 4: Commit**

```bash
git add desktop/src/App.vue
git commit -m "$(cat <<'EOF'
feat: show BOSS job list controls in desktop shell

Send boss.* WS commands and render returned jobs.
EOF
)"
```

---

### Task 5: 文档与端到端核对

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 更新 README 使用说明**

在「开发」节后增加「BOSS 列表（v1）」：

```markdown
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
```

（注意：外层 README 已是 markdown；实现时写成合法嵌套，代码块用缩进或分开两段，避免围栏冲突。）
- [ ] **Step 2: 跑全量测试**

```bash
uv run pytest tests/boss -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs: document BOSS list v1 usage

EOF
)"
```

---

## Spec Coverage Checklist

| Spec 项 | Task |
|---------|------|
| Patchright `connect_over_cdp` | Task 2 |
| 默认 CDP `9222` / `GHOSTJOB_CDP_URL` | Task 2 |
| 断开连接不杀 Chrome | Task 2 + 3 |
| `boss.open` / `search` / `close` + status/jobs/error | Task 3 |
| 默认搜索 URL | Task 1 + 3 |
| 列表字段 title/company/salary/link/jobId | Task 1 |
| need_login / busy / CDP 失败文案 | Task 2 + 3 |
| Vue 按钮与列表 | Task 4 |
| 不做详情/投递/翻页/内嵌页/独立 profile | 全任务未包含 = OK |

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-23-boss-patchright-jobs.md`.

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每任务派一个新子代理，任务间人工/自动复核  
2. **Inline Execution** — 本会话按 executing-plans 连续执行并设检查点  

选哪一种？
