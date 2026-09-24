from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from patchright.async_api import BrowserContext, Locator, Page, Response, async_playwright

from backend.boss.jobs import (
    ADDRESS_SELECTORS,
    BASE_URL,
    CARD_SELECTOR,
    COMPANY_SELECTORS,
    DEFAULT_SEARCH_URL,
    DESCRIPTION_SELECTORS,
    DETAIL_PANEL_SELECTOR,
    HR_NAME_SELECTORS,
    HR_TITLE_SELECTORS,
    JOBLIST_API_MARKER,
    Job,
    JobDetail,
    JobInfo,
    LINK_SELECTORS,
    LOCATION_SELECTORS,
    SALARY_SELECTORS,
    TAG_LIST_SELECTOR,
    TITLE_SELECTORS,
    is_detail_api_url,
    job_detail_from_detail_payload,
    job_detail_from_list_item,
    job_id_from_link,
    job_info_from_api_item,
    joblist_items_from_payload,
    looks_like_login_wall,
    merge_job_detail,
    merge_job_info,
    print_job,
    resolve_salary,
    salary_map_from_joblist_payload,
)

MAX_SCROLL_BATCHES = 20

OnJobCallback = Callable[[Job], Awaitable[None] | None]


def _should_stop_scroll(*, stop: bool, empty_streak: int, batch_idx: int) -> bool:
    return stop or empty_streak >= 2 or batch_idx >= MAX_SCROLL_BATCHES


def api_item_by_job_id(items: list[dict[str, Any]], job_id: str | None) -> dict[str, Any] | None:
    if not job_id:
        return None
    for it in items:
        if str(it.get("encryptJobId") or "") == job_id:
            return it
    return None


def _merge_api_items(api_items: list[dict[str, Any]], items: list[dict[str, Any]]) -> None:
    """按 encryptJobId 去重追加，不清空已有项。"""
    known = {str(it.get("encryptJobId") or "") for it in api_items if it.get("encryptJobId")}
    for it in items:
        eid = str(it.get("encryptJobId") or "")
        if eid:
            if eid in known:
                continue
            known.add(eid)
        api_items.append(it)


def default_user_data_dir() -> Path:
    return Path.home() / ".ghostjob" / "chrome-profile"


class BossSession:
    def __init__(self, user_data_dir: Path | None = None) -> None:
        self.user_data_dir = user_data_dir or default_user_data_dir()
        self._playwright = None
        self._context: BrowserContext | None = None
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        self._stop.set()

    def clear_stop(self) -> None:
        self._stop.clear()

    def _stopped(self) -> bool:
        return self._stop.is_set()

    @property
    def is_open(self) -> bool:
        return self._context is not None

    async def open(self) -> None:
        if self._context is not None:
            return
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        try:
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.user_data_dir),
                channel="chrome",
                headless=False,
                no_viewport=True,
            )
        except Exception as exc:  # noqa: BLE001
            await self.close()
            msg = str(exc).lower()
            if "channel" in msg or "chrome" in msg:
                raise RuntimeError(
                    "无法启动本机 Chrome（channel=chrome）。请确认已安装 Google Chrome。"
                ) from exc
            if "user data" in msg or "lock" in msg or "in use" in msg or "singleton" in msg:
                raise RuntimeError(
                    f"Chrome profile 被占用：{self.user_data_dir}。"
                    "请关闭其它使用该目录的 Chrome 后重试。"
                ) from exc
            raise RuntimeError(f"启动 Chrome 失败：{exc}") from exc

    async def close(self) -> None:
        ctx = self._context
        self._context = None
        if ctx is not None:
            try:
                await ctx.close()
            except Exception:  # noqa: BLE001
                pass
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:  # noqa: BLE001
                pass
            self._playwright = None

    async def _page(self) -> Page:
        if self._context is None:
            raise RuntimeError("BossSession 未打开，请先 boss.open")
        if self._context.pages:
            return self._context.pages[0]
        return await self._context.new_page()

    async def _first_text(self, root: Locator, selectors: tuple[str, ...]) -> str:
        for sel in selectors:
            try:
                text = (await root.locator(sel).first.inner_text(timeout=800)).strip()
                if text:
                    return text
            except Exception:  # noqa: BLE001
                continue
        return ""

    async def _first_href(self, root: Locator, selectors: tuple[str, ...]) -> str:
        for sel in selectors:
            try:
                href = await root.locator(sel).first.get_attribute("href", timeout=800)
                if href:
                    return href
            except Exception:  # noqa: BLE001
                continue
        return ""

    async def _tag_experience_education(self, card: Locator) -> tuple[str, str]:
        try:
            tags = await card.locator(TAG_LIST_SELECTOR).all_inner_texts()
        except Exception:  # noqa: BLE001
            return "", ""
        cleaned = [t.strip() for t in tags if t.strip()]
        experience = cleaned[0] if len(cleaned) > 0 else ""
        education = cleaned[1] if len(cleaned) > 1 else ""
        return experience, education

    async def _job_info_from_card(
        self,
        card: Locator,
        index: int,
        *,
        salary_by_id: dict[str, str],
        api_items: list[dict[str, Any]],
    ) -> JobInfo:
        title = await self._first_text(card, TITLE_SELECTORS)
        dom_salary = await self._first_text(card, SALARY_SELECTORS)
        company = await self._first_text(card, COMPANY_SELECTORS)
        location = await self._first_text(card, LOCATION_SELECTORS)
        experience, education = await self._tag_experience_education(card)
        href = await self._first_href(card, LINK_SELECTORS)
        link = urljoin(BASE_URL, href) if href else ""
        job_id = await card.get_attribute("data-jobid") or job_id_from_link(link)
        if not title:
            try:
                blob = (await card.inner_text(timeout=1_000)).strip()
                title = blob.splitlines()[0].strip() if blob else f"card-{index}"
            except Exception:  # noqa: BLE001
                title = f"card-{index}"

        api_item = api_item_by_job_id(api_items, job_id)
        if api_item is None and 0 <= index < len(api_items):
            api_item = api_items[index]
        api_info = (
            job_info_from_api_item(api_item, link=link, job_id=job_id) if api_item else None
        )
        salary = resolve_salary(
            dom_salary=dom_salary,
            job_id=job_id,
            salary_by_id=salary_by_id,
            api_items=api_items,
            index=index,
        )
        dom = JobInfo(
            title=title,
            salary=dom_salary,
            company=company,
            location=location,
            experience=experience,
            education=education,
            link=link,
            job_id=job_id,
        )
        return merge_job_info(dom, api_info, salary=salary)

    async def _read_detail_from_dom(self, page: Page) -> JobDetail:
        try:
            await page.wait_for_selector(DETAIL_PANEL_SELECTOR, timeout=8_000)
        except Exception:  # noqa: BLE001
            return JobDetail()
        description = await self._first_text(page.locator("body"), DESCRIPTION_SELECTORS)
        # 限定在详情容器内找 HR / 地址，减少误匹配
        panel = page.locator(DETAIL_PANEL_SELECTOR).first
        hr_name = await self._first_text(panel, HR_NAME_SELECTORS)
        hr_title = await self._first_text(panel, HR_TITLE_SELECTORS)
        address = await self._first_text(panel, ADDRESS_SELECTORS)
        if not description:
            try:
                description = (await panel.locator(DESCRIPTION_SELECTORS[0]).first.inner_text(timeout=1_000)).strip()
            except Exception:  # noqa: BLE001
                pass
        return JobDetail(
            description=description,
            hr_name=hr_name,
            hr_title=hr_title,
            address=address,
        )

    async def _scrape_unseen_cards_with_details(
        self,
        page: Page,
        *,
        salary_by_id: dict[str, str],
        api_items: list[dict[str, Any]],
        seen: set[str],
        on_job: OnJobCallback | None = None,
        stop_check: Callable[[], bool] | None = None,
    ) -> list[Job]:
        cards = page.locator(CARD_SELECTOR)
        count = await cards.count()
        print(
            f"[boss] 当前页卡片数: {count}; API 职位数: {len(api_items)}; "
            f"明文薪资映射: {len(salary_by_id)}; 已见: {len(seen)}",
            flush=True,
        )
        enriched: list[Job] = []
        for i in range(count):
            if stop_check and stop_check():
                break
            card = cards.nth(i)
            try:
                info = await self._job_info_from_card(
                    card, i, salary_by_id=salary_by_id, api_items=api_items
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[boss] card[{i}] 列表字段失败: {exc}", flush=True)
                info = JobInfo(title=f"card-{i}")

            if info.job_id and info.job_id in seen:
                continue

            list_detail = job_detail_from_list_item(api_item_by_job_id(api_items, info.job_id))
            api_detail = JobDetail()
            dom_detail = JobDetail()

            async def on_detail_response(response: Response) -> None:
                nonlocal api_detail
                if response.status != 200 or not is_detail_api_url(response.url):
                    return
                try:
                    payload = await response.json()
                except Exception:  # noqa: BLE001
                    return
                if isinstance(payload, dict):
                    api_detail = merge_job_detail(
                        api_detail, job_detail_from_detail_payload(payload)
                    )

            page.on("response", on_detail_response)
            try:
                try:
                    async with page.expect_response(
                        lambda r: r.status == 200 and is_detail_api_url(r.url),
                        timeout=8_000,
                    ) as detail_info:
                        await card.click(timeout=5_000)
                    try:
                        payload = await (await detail_info.value).json()
                        if isinstance(payload, dict):
                            api_detail = merge_job_detail(
                                api_detail, job_detail_from_detail_payload(payload)
                            )
                    except Exception:  # noqa: BLE001
                        pass
                except Exception:
                    try:
                        await card.click(timeout=5_000)
                    except Exception as exc:  # noqa: BLE001
                        print(f"[boss] card[{i}] 点击失败: {exc}", flush=True)
                try:
                    dom_detail = await self._read_detail_from_dom(page)
                except Exception as exc:  # noqa: BLE001
                    print(f"[boss] card[{i}] 详情 DOM 失败: {exc}", flush=True)
            finally:
                page.remove_listener("response", on_detail_response)

            detail = merge_job_detail(api_detail, list_detail, dom_detail)
            job = Job(info=info, detail=detail)
            print_job(job)
            enriched.append(job)
            if info.job_id:
                seen.add(info.job_id)
            if on_job is not None:
                maybe = on_job(job)
                if inspect.isawaitable(maybe):
                    await maybe
        return enriched

    async def search(
        self,
        url: str | None = None,
        *,
        on_job: OnJobCallback | None = None,
    ) -> tuple[str, list[Job], str]:
        self.clear_stop()
        if self._context is None:
            await self.open()
        target = url or DEFAULT_SEARCH_URL
        page = await self._page()

        salary_by_id: dict[str, str] = {}
        api_items: list[dict[str, Any]] = []

        async def on_response(response: Response) -> None:
            if JOBLIST_API_MARKER not in response.url or response.status != 200:
                return
            try:
                payload = await response.json()
            except Exception:  # noqa: BLE001
                return
            if not isinstance(payload, dict):
                return
            salary_by_id.update(salary_map_from_joblist_payload(payload))
            items = joblist_items_from_payload(payload)
            if items:
                _merge_api_items(api_items, items)

        page.on("response", on_response)
        try:
            try:
                async with page.expect_response(
                    lambda r: JOBLIST_API_MARKER in r.url and r.status == 200,
                    timeout=25_000,
                ) as resp_info:
                    await page.goto(target, wait_until="domcontentloaded")
                try:
                    payload = await (await resp_info.value).json()
                    if isinstance(payload, dict):
                        salary_by_id.update(salary_map_from_joblist_payload(payload))
                        items = joblist_items_from_payload(payload)
                        if items:
                            _merge_api_items(api_items, items)
                except Exception:  # noqa: BLE001
                    pass
            except Exception as exc:  # noqa: BLE001
                print(f"[boss] 等待 {JOBLIST_API_MARKER} 失败: {exc}，继续 DOM/已捕获响应", flush=True)
                if "zhipin.com" not in (page.url or ""):
                    await page.goto(target, wait_until="domcontentloaded")

            try:
                await page.wait_for_selector(CARD_SELECTOR, timeout=20_000)
            except Exception:  # noqa: BLE001
                html = await page.content()
                final = page.url
                if looks_like_login_wall(html, final):
                    return final, [], "need_login"
                return final, [], "done"

            html = await page.content()
            final = page.url
            if looks_like_login_wall(html, final):
                return final, [], "need_login"

            all_jobs: list[Job] = []
            seen: set[str] = set()
            empty_streak = 0
            batch_idx = 0
            while not _should_stop_scroll(
                stop=self._stopped(), empty_streak=empty_streak, batch_idx=batch_idx
            ):
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

                prev_count = await page.locator(CARD_SELECTOR).count()
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                try:
                    async with page.expect_response(
                        lambda r: JOBLIST_API_MARKER in r.url and r.status == 200,
                        timeout=8_000,
                    ):
                        pass
                except Exception:  # noqa: BLE001
                    await page.wait_for_timeout(1_500)
                after = await page.locator(CARD_SELECTOR).count()
                if after <= prev_count and not new_jobs:
                    empty_streak += 1
                else:
                    empty_streak = 0
                batch_idx += 1

            state = "stopped" if self._stopped() else "done"
            return page.url, all_jobs, state
        finally:
            page.remove_listener("response", on_response)
