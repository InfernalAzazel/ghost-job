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
