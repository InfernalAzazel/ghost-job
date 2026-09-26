"""BOSS 自动投递会话状态。"""

from __future__ import annotations

from datetime import datetime

import reflex as rx
from patchright.async_api import Error as PlaywrightError
from sqlalchemy.exc import SQLAlchemyError

from job.boss.filters import KeywordFilter, PaceProfile, SearchUrl
from job.boss.jobs import JobScraper
from job.boss.review import JobReviewer
from job.boss.session import BossSession
from job.models import init_db
from job.models.job import JobRow
from job.models.search import SearchConfigRow
from job.models.setting import LlmSettings

_session = BossSession()
_scraper = JobScraper(_session)

# 投递结束状态 → 状态文案
_STATUS = {
    "done": "已完成",
    "stopped": "已停止",
    "need_login": "需要登录",
    "limit": "今日已达上限",
}
# 投递结束状态 → 日志文案
_FINISHED = {
    "done": "所选城市的岗位都看完了",
    "stopped": "已停止投递",
    "need_login": "需要登录 BOSS，请在浏览器里登录后重新开始",
    "limit": "今日投递次数已用完，明天再来",
}
# 日志最多保留条数
_MAX_LOG = 200


class BossState(rx.State):
    boss_state: str = "空闲"
    busy: bool = False
    # 运行日志（新的在前）：{time, level, text}，level 为 info / ok / dup / skip / warn
    log: list[dict[str, str]] = rx.field(default_factory=list)
    stored_count: int = 0
    session_count: int = 0
    # 本次投递中遇到的重复岗位数与跳过岗位数
    dup_count: int = 0
    skip_count: int = 0
    # 目标城市（顿号分隔，工作台展示用）
    target_cities: str = ""

    def _push_log(self, text: str, level: str = "info") -> None:
        """追加一条运行日志。"""
        now = datetime.now().astimezone().strftime("%H:%M:%S")
        self.log = [{"time": now, "level": level, "text": text}, *self.log][:_MAX_LOG]

    def _refresh_stored_count(self) -> None:
        self.stored_count = JobRow.count_applied()

    def _refresh_target_cities(self) -> None:
        targets = SearchUrl.by_city(SearchConfigRow.load())
        self.target_cities = "、".join(city for city, _ in targets)

    @rx.event
    def on_load(self):
        init_db()
        self._refresh_stored_count()
        self._refresh_target_cities()
        if not self.log:
            self._push_log(f"已就绪，累计投递 {self.stored_count} 个岗位")

    @rx.event
    def clear_log(self):
        self.log = []

    @rx.event
    def stop_apply(self):
        _scraper.request_stop()
        self._push_log("正在停止，处理完当前岗位后结束")
        self.boss_state = "停止中"

    @rx.event
    async def close_boss(self):
        await _session.close()
        self.boss_state = "空闲"
        self.busy = False
        self._push_log("浏览器已关闭")

    @rx.event(background=True)
    async def start_apply(self):
        """按求职配置逐个城市自动投递；浏览器未打开时自动打开。"""
        async with self:
            if self.busy:
                return
            config = SearchConfigRow.load()
            query = str(config.get("query") or "").strip()
            if not query:
                self._push_log("请先在配置中心填写岗位关键词", "warn")
                self.boss_state = "待完善配置"
                return
            targets = SearchUrl.by_city(config)
            pace = PaceProfile.from_config(config)
            keywords = KeywordFilter.from_config(config)
            reviewer = JobReviewer.from_config(config, LlmSettings.load())
            resume = str(config.get("resume_text") or "").strip()
            if config.get("resume_match") and not resume:
                self._push_log(
                    "已开启简历技术匹配，请先在「简历配置」上传简历", "warn"
                )
                self.boss_state = "待完善简历"
                return
            if JobRow.count_today() >= JobScraper.DAILY_LIMIT:
                self._push_log(_FINISHED["limit"], "warn")
                self.boss_state = _STATUS["limit"]
                return
            if reviewer and not reviewer.llm.ready:
                self._push_log(
                    "已开启 AI 筛选，请先在配置中心开通「AI 服务」", "warn"
                )
                self.boss_state = "待开通 AI 服务"
                return
            self.busy = True
            self.boss_state = "准备中"
            self.session_count = 0
            self.dup_count = 0
            self.skip_count = 0
            self.target_cities = "、".join(city for city, _ in targets)
            self._push_log(f"开始自动投递：{query} · {self.target_cities}")
            self._push_log(f"投递节奏：{pace.describe()}")
            if not _session.is_open:
                self._push_log("正在打开浏览器…")
            if reviewer:
                self._push_log(f"已开启：{'、'.join(reviewer.checks)}")

        async def on_job(_job) -> None:
            async with self:
                self.session_count += 1
                self._refresh_stored_count()
                self.boss_state = "投递中"

        async def on_log(level: str, text: str) -> None:
            async with self:
                if self.boss_state == "准备中":
                    self.boss_state = "投递中"
                if level == "dup":
                    self.dup_count += 1
                elif level == "skip":
                    self.skip_count += 1
                self._push_log(text, level)

        try:
            _jobs, state = await _scraper.search(
                targets,
                pace=pace,
                keywords=keywords,
                reviewer=reviewer,
                on_job=on_job,
                on_log=on_log,
            )
            async with self:
                self.boss_state = _STATUS.get(state, "已完成")
                self._refresh_stored_count()
                self._push_log(
                    f"{_FINISHED.get(state, state)}：本次投递 {self.session_count} 条，"
                    f"重复 {self.dup_count} 条，跳过 {self.skip_count} 条，"
                    f"累计投递 {self.stored_count} 条",
                    "warn" if state in ("need_login", "limit") else "info",
                )
                self.busy = False
        except (RuntimeError, PlaywrightError, SQLAlchemyError) as exc:
            async with self:
                self.boss_state = "出错"
                self._push_log(str(exc), "warn")
                self.busy = False
