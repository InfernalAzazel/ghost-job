"""查企业弹窗：岗位管理和消息页共用。"""

from __future__ import annotations

import re
import webbrowser
from pathlib import Path

import reflex as rx
from patchright.async_api import Error as PlaywrightError
from pydantic_ai.exceptions import AgentRunError
from sqlalchemy.exc import SQLAlchemyError

from job.boss.company import CompanyChecker, CompanyPage, CompanyReviewer, CompanySearch
from job.boss.company_report import company_pdf
from job.models.company import CompanyRow
from job.models.job import JobRow
from job.models.setting import LlmSettings
from job.ui.state.boss import _session
from job.ui.state.export import BROWSER_DOWNLOAD, save_dialog_script
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

    def _pdf_name(self) -> str:
        name = self.report.get("full_name") or self.report.get("name") or "企业"
        return re.sub(r'[\\/:*?"<>|]', "_", f"{name}-企业报告.pdf")

    @rx.event
    def download_report(self):
        script = save_dialog_script(self._pdf_name(), "PDF", "pdf")
        return rx.call_script(script, callback=CompanyState.save_report)

    @rx.event
    def save_report(self, path: str | None):
        """把报告 PDF 写到保存框选中的路径；取消时 ``path`` 为空。"""
        if not path or not self.report:
            return None
        data = company_pdf(self.report)
        if path == BROWSER_DOWNLOAD:
            return rx.download(data=data, filename=self._pdf_name())
        try:
            Path(path).write_bytes(data)
        except OSError as exc:
            return rx.toast.error(f"下载失败：{exc.strerror or exc}")
        return rx.toast.success(f"报告已保存到 {path}")

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
