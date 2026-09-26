"""Reflex app entry: routes and pages."""

from __future__ import annotations

import reflex as rx

from job.ui.pages.config import ConfigPage
from job.ui.pages.jobs import JobsPage
from job.ui.pages.messages import MessagesPage
from job.ui.pages.workbench import WorkbenchPage
from job.ui.state.boss import BossState
from job.ui.state.config import ConfigState
from job.ui.state.jobs import JobsState
from job.ui.state.llm import LlmState
from job.ui.state.messages import MessagesState

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
    MessagesPage.create,
    route="/messages",
    title="消息 · Ghost Job",
    on_load=MessagesState.on_load,
)
app.add_page(
    ConfigPage.create,
    route="/config",
    title="配置中心 · Ghost Job",
    on_load=[ConfigState.on_load, LlmState.on_load],
)
