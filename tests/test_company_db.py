"""公司查询结果入库，以及岗位、会话列表带出风险等级。"""

from __future__ import annotations

from pathlib import Path

import pytest

from job import models as models_pkg
from job.boss.chat import ChatMessage
from job.boss.jobs import Job
from job.models import init_db, reset_engine
from job.models.chat import ChatMessageRow
from job.models.company import CompanyRow
from job.models.job import JobRow


@pytest.fixture
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(models_pkg, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(models_pkg, "DATA_DIR", tmp_path)
    reset_engine()
    init_db()
    yield
    reset_engine()


def _save(brand_id: str = "b1", risk: str = "medium") -> None:
    CompanyRow.save(
        brand_id,
        name="昊誉",
        full_name="广州昊誉信息科技有限公司",
        info={"企业名称": "广州昊誉信息科技有限公司", "经营状态": "在营"},
        hits=[{"title": "标题", "href": "https://a.com", "body": "摘要", "query": "员工评价"}],
        risk=risk,
        summary="有少量劳动纠纷",
        points=[{"text": "2023 年劳动仲裁 1 起", "href": "https://a.com"}],
    )


def test_save_and_get_dict(tmp_db):
    assert CompanyRow.get_dict("b1") is None
    _save()
    item = CompanyRow.get_dict("b1")
    assert item["full_name"] == "广州昊誉信息科技有限公司"
    assert item["info"] == [{"label": "企业名称", "value": "广州昊誉信息科技有限公司"}, {"label": "经营状态", "value": "在营"}]
    assert (item["risk"], item["risk_label"]) == ("medium", "中风险")
    assert item["points"][0]["href"] == "https://a.com"
    assert item["checked_at"]

    _save(risk="high")
    assert CompanyRow.get_dict("b1")["risk"] == "high"
    assert CompanyRow.risks(["b1", "b2", ""]) == {"b1": "high"}


def test_job_and_conversation_lists_carry_risk(tmp_db):
    JobRow.record(Job(job_id="j1", title="AI 工程师", company="昊誉", brand_id="b1"))
    JobRow.record(Job(job_id="j2", title="后端", company="别家"))
    _save()

    jobs = {j["uid"]: j for j in JobRow.list_dicts()}
    assert (jobs["j1"]["brandId"], jobs["j1"]["risk"], jobs["j1"]["riskLabel"]) == ("b1", "medium", "中风险")
    assert (jobs["j2"]["risk"], jobs["j2"]["riskLabel"]) == ("", "")
    assert JobRow.get_dict("j1")["risk"] == "medium"

    ChatMessageRow.record_new(
        [ChatMessage(mid="m1", from_hr=True, text="您好")], job_uid="j1", boss_id="boss-1", hr_name="梁女士"
    )
    item = ChatMessageRow.conversations()[0]
    assert (item["risk"], item["risk_label"]) == ("medium", "中风险")
