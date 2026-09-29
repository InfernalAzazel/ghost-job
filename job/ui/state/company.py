"""查企业弹窗：岗位管理和消息页共用。"""

from __future__ import annotations

import webbrowser

import reflex as rx
from patchright.async_api import Error as PlaywrightError
from pydantic_ai.exceptions import AgentRunError
from sqlalchemy.exc import SQLAlchemyError

from job.boss.company import CompanyChecker, CompanyPage, CompanyReviewer, CompanySearch
from job.models.company import CompanyRow
from job.models.job import JobRow
from job.models.setting import LlmSettings
from job.ui.state.boss import _session
from job.ui.state.jobs import JobsState
from job.ui.state.messages import MessagesState


class CompanyState(rx.State):
    open: bool = False
    # 查询中、当前步骤与出错提示
    busy: bool = False
    step: str = ""
    error: str = ""
    job_uid: str = ""
    # 查询前先显示的公司简称
    company: str = ""
    # CompanyRow.get_dict 的结果；没查过为空
    report: rx.Field[dict] = rx.field(default_factory=dict)

    @rx.var
    def has_report(self) -> bool:
        return bool(self.report)

    @rx.event
    def show(self, job_uid: str, company: str):
        """打开弹窗：查过的直接显示上次结果，没查过的开始查询。"""
        if self.busy and job_uid != self.job_uid:
            return rx.toast.info("正在查询另一家公司，请稍候")
        self.job_uid, self.company, self.error = job_uid, company, ""
        job = JobRow.get_dict(job_uid)
        brand_id = job["brandId"] if job else ""
        self.report = (CompanyRow.get_dict(brand_id) if brand_id else None) or {}
        self.open = True
        if not self.report and not self.busy:
            return CompanyState.check
        return None

    @rx.event
    def set_open(self, value: bool) -> None:
        self.open = value

    @rx.event
    def open_link(self, url: str) -> None:
        webbrowser.open(url)

    @rx.event(background=True)
    async def check(self):
        """重新查询：公司主页 → 网上搜索 → AI 评估，约半分钟。"""
        async with self:
            if self.busy:
                return
            self.busy, self.error, self.step = True, "", "正在打开浏览器…"
            job_uid = self.job_uid
        llm = LlmSettings.load()
        checker = CompanyChecker(
            CompanyPage(_session),
            CompanySearch(),
            CompanyReviewer(llm=llm) if llm.ready else None,
        )

        async def on_step(text: str) -> None:
            async with self:
                self.step = text

        try:
            brand_id = await checker.check(job_uid, on_step)
        except (RuntimeError, PlaywrightError, AgentRunError, SQLAlchemyError) as exc:
            async with self:
                self.busy, self.step = False, ""
                self.error = str(exc) or "查询失败，请稍后重试"
            return
        async with self:
            self.busy, self.step = False, ""
            if self.job_uid == job_uid:
                self.report = CompanyRow.get_dict(brand_id) or {}
        yield JobsState.refresh
        yield MessagesState.refresh
