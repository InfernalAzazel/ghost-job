"""Reflex app entry: routes and pages."""

from __future__ import annotations

import reflex as rx

from job.ui.pages.config import ConfigPage
from job.ui.pages.jobs import JobsPage
from job.ui.pages.workbench import WorkbenchPage
from job.ui.state import BossState, JobsState, LlmState, PlansState

app = rx.App(
    style={
        "html": {"height": "100%", "overflow": "hidden"},
        "body": {"height": "100%", "overflow": "hidden", "margin": "0"},
    },
)
app.add_page(
    WorkbenchPage.create,
    route="/",
    title="Ghost Job",
    on_load=BossState.on_load,
)
app.add_page(
    JobsPage.create,
    route="/jobs",
    title="岗位管理 · Ghost Job",
    on_load=JobsState.on_load,
)
app.add_page(
    ConfigPage.create,
    route="/config",
    title="配置中心 · Ghost Job",
    on_load=[PlansState.on_load, LlmState.on_load],
)
