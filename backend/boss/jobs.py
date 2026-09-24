from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from pydantic import BaseModel, ConfigDict, Field
from pyquery import PyQuery as pq

DEFAULT_SEARCH_URL = (
    "https://www.zhipin.com/web/geek/jobs"
    "?city=101280100&jobType=1901&query=ai应用开发"
)
BASE_URL = "https://www.zhipin.com"
JOBLIST_API_MARKER = "joblist.json"

CARD_SELECTOR = "li.job-card-box, .job-card-wrapper"
TITLE_SELECTORS = (".job-name", "a.job-name", ".job-title .job-name")
SALARY_SELECTORS = (".salary", ".job-salary")
COMPANY_SELECTORS = (".company-name", ".boss-name", "a.boss-info .boss-name")
LOCATION_SELECTORS = (".company-location", ".job-area", ".job-area-wrapper")
LINK_SELECTORS = ("a.job-name", "a.job-card-left", "a[href*='job_detail']", "a")
TAG_LIST_SELECTOR = ".tag-list li"
LOGIN_HINT_SELECTOR = ".login-dialog-wrap"
DETAIL_PANEL_SELECTOR = (
    ".job-detail-box, .job-detail-body, .job-detail-container, .job-body, .job-detail"
)
DESCRIPTION_SELECTORS = (
    ".job-sec-text",
    ".job-detail-section .text",
    ".job-detail-body .job-sec-text",
    ".job-detail-box .job-sec-text",
    ".job-detail-box .desc",
    ".detail-content",
    ".job-detail .detail-content",
)
HR_NAME_SELECTORS = (
    ".job-boss-info .name",
    ".job-detail-box .job-boss-info .name",
    ".boss-info-attr .name",
)
HR_TITLE_SELECTORS = (
    ".job-boss-info .boss-title",
    ".job-boss-info .title",
    ".job-detail-box .job-boss-info .boss-title",
)
ADDRESS_SELECTORS = (
    ".job-address",
    ".location-address",
    ".job-location .location-address",
    ".job-detail-box .location-address",
)
DETAIL_API_MARKERS = ("job/detail.json", "job/card.json")

_PUA_RE = re.compile(r"[\ue000-\uf8ff]")


class JobInfo(BaseModel):
    """列表卡片摘要：标题 / 薪资 / 公司 / 地点 / 经验 / 学历。"""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    title: str
    salary: str = ""
    company: str = ""
    location: str = ""
    experience: str = ""
    education: str = ""
    link: str = ""
    job_id: str | None = Field(default=None, serialization_alias="jobId")


class JobDetail(BaseModel):
    """详情：职位描述 + HR + 详细工作地址。"""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    description: str = ""
    hr_name: str = Field(default="", serialization_alias="hrName")
    hr_title: str = Field(default="", serialization_alias="hrTitle")
    address: str = ""


class Job(BaseModel):
    """一次抓取结果 = 摘要 + 详情。"""

    model_config = ConfigDict(frozen=True)

    info: JobInfo
    detail: JobDetail = Field(default_factory=JobDetail)

    def to_ws(self) -> dict[str, str | None]:
        data = self.info.model_dump(by_alias=True)
        data.update(self.detail.model_dump(by_alias=True))
        return data


def job_to_dict(job: Job) -> dict[str, str | None]:
    return job.to_ws()


def print_job(job: Job) -> None:
    info = job.info
    detail = job.detail
    sep = "=" * 60
    lines = [
        sep,
        f"标题: {info.title}",
        f"薪资: {info.salary}",
        f"公司: {info.company}",
        f"地点: {info.location}",
        f"经验: {info.experience}",
        f"学历: {info.education}",
        f"链接: {info.link}",
    ]
    if info.job_id:
        lines.append(f"jobId: {info.job_id}")
    lines += [
        f"HR: {detail.hr_name or '(空)'} · {detail.hr_title or '(空)'}",
        f"详细地址: {detail.address or '(空)'}",
        "--- 职位描述 ---",
        detail.description or "(空)",
        sep,
    ]
    print("\n".join(lines), flush=True)


def looks_like_font_encrypted(text: str) -> bool:
    return bool(text and _PUA_RE.search(text))


def job_id_from_link(link: str) -> str | None:
    m = re.search(r"/job_detail/([^./?#]+)", link)
    return m.group(1) if m else None


def format_location(*parts: str | None) -> str:
    return "·".join(p.strip() for p in parts if p and str(p).strip())


def salary_map_from_joblist_payload(payload: dict[str, Any]) -> dict[str, str]:
    zp = payload.get("zpData") if isinstance(payload, dict) else None
    out: dict[str, str] = {}
    for item in (zp or {}).get("jobList") or []:
        if not isinstance(item, dict):
            continue
        eid = str(item.get("encryptJobId") or "").strip()
        salary = str(item.get("salaryDesc") or "").strip()
        if eid and salary and not looks_like_font_encrypted(salary):
            out[eid] = salary
    return out


def joblist_items_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    zp = payload.get("zpData") if isinstance(payload, dict) else None
    raw = (zp or {}).get("jobList") or []
    return [x for x in raw if isinstance(x, dict)]


def job_info_from_api_item(
    item: dict[str, Any],
    *,
    link: str = "",
    job_id: str | None = None,
) -> JobInfo:
    return JobInfo(
        title=str(item.get("jobName") or "").strip(),
        salary=str(item.get("salaryDesc") or "").strip(),
        company=str(item.get("brandName") or "").strip(),
        location=format_location(
            item.get("cityName"),
            item.get("areaDistrict"),
            item.get("businessDistrict"),
        ),
        experience=str(item.get("jobExperience") or "").strip(),
        education=str(item.get("jobDegree") or "").strip(),
        link=link,
        job_id=job_id or str(item.get("encryptJobId") or "").strip() or None,
    )


def resolve_salary(
    *,
    dom_salary: str,
    job_id: str | None,
    salary_by_id: dict[str, str],
    api_items: list[dict[str, Any]],
    index: int,
) -> str:
    if job_id and job_id in salary_by_id:
        return salary_by_id[job_id]
    if 0 <= index < len(api_items):
        api_salary = str(api_items[index].get("salaryDesc") or "").strip()
        if api_salary and not looks_like_font_encrypted(api_salary):
            return api_salary
    if dom_salary and not looks_like_font_encrypted(dom_salary):
        return dom_salary
    return ""


def merge_job_info(dom: JobInfo, api: JobInfo | None, *, salary: str) -> JobInfo:
    """DOM 与 API 互补；薪资以 resolve 结果为准。"""
    if api is None:
        return dom.model_copy(update={"salary": salary or dom.salary})
    return JobInfo(
        title=dom.title if dom.title and not dom.title.startswith("card-") else api.title or dom.title,
        salary=salary or api.salary or dom.salary,
        company=dom.company or api.company,
        location=dom.location or api.location,
        experience=dom.experience or api.experience,
        education=dom.education or api.education,
        link=dom.link or api.link,
        job_id=dom.job_id or api.job_id,
    )


def job_detail_from_list_item(item: dict[str, Any] | None) -> JobDetail:
    """列表 API 可先带出 HR；详细地址通常要等详情接口/面板。"""
    if not item:
        return JobDetail()
    return JobDetail(
        hr_name=str(item.get("bossName") or "").strip(),
        hr_title=str(item.get("bossTitle") or "").strip(),
    )


def job_detail_from_detail_payload(payload: dict[str, Any]) -> JobDetail:
    """解析 job/detail.json 或 job/card.json。"""
    zp = payload.get("zpData") if isinstance(payload, dict) else None
    if not isinstance(zp, dict):
        return JobDetail()

    job_info = zp.get("jobInfo") if isinstance(zp.get("jobInfo"), dict) else {}
    boss_info = zp.get("bossInfo") if isinstance(zp.get("bossInfo"), dict) else {}
    card = zp.get("jobCard") if isinstance(zp.get("jobCard"), dict) else {}

    description = str(
        job_info.get("postDescription")
        or card.get("postDescription")
        or card.get("jobDesc")
        or ""
    ).strip()
    address = str(job_info.get("address") or card.get("address") or "").strip()
    hr_name = str(boss_info.get("name") or card.get("bossName") or "").strip()
    hr_title = str(boss_info.get("title") or card.get("bossTitle") or "").strip()
    return JobDetail(
        description=description,
        hr_name=hr_name,
        hr_title=hr_title,
        address=address,
    )


def merge_job_detail(*parts: JobDetail) -> JobDetail:
    """后写不覆盖已有非空字段（优先保留先到的完整值，空则用后者补）。"""
    description = hr_name = hr_title = address = ""
    for part in parts:
        description = description or part.description
        hr_name = hr_name or part.hr_name
        hr_title = hr_title or part.hr_title
        address = address or part.address
    return JobDetail(
        description=description,
        hr_name=hr_name,
        hr_title=hr_title,
        address=address,
    )


def is_detail_api_url(url: str) -> bool:
    return any(m in url for m in DETAIL_API_MARKERS)


def _pick_text(card: pq, selectors: tuple[str, ...]) -> str:
    return next((t for sel in selectors if (t := card(sel).eq(0).text().strip())), "")


def _pick_href(card: pq, selectors: tuple[str, ...]) -> str:
    return next((h for sel in selectors if (h := card(sel).eq(0).attr("href"))), "")


def _tags_experience_education(card: pq) -> tuple[str, str]:
    tags = [t.text().strip() for t in card(TAG_LIST_SELECTOR).items() if t.text().strip()]
    experience = tags[0] if len(tags) > 0 else ""
    education = tags[1] if len(tags) > 1 else ""
    return experience, education


def parse_jobs_from_html(html: str) -> list[Job]:
    jobs: list[Job] = []
    for card in pq(html)(CARD_SELECTOR).items():
        title = _pick_text(card, TITLE_SELECTORS)
        if not title:
            continue
        href = _pick_href(card, LINK_SELECTORS)
        link = urljoin(BASE_URL, href) if href else ""
        experience, education = _tags_experience_education(card)
        info = JobInfo(
            title=title,
            salary=_pick_text(card, SALARY_SELECTORS),
            company=_pick_text(card, COMPANY_SELECTORS),
            location=_pick_text(card, LOCATION_SELECTORS),
            experience=experience,
            education=education,
            link=link,
            job_id=card.attr("data-jobid") or job_id_from_link(link),
        )
        jobs.append(Job(info=info))
    return jobs


def looks_like_login_wall(html: str, url: str = "") -> bool:
    del url
    if parse_jobs_from_html(html):
        return False
    for node in pq(html)(LOGIN_HINT_SELECTOR).items():
        style = (node.attr("style") or "").replace(" ", "").lower()
        if "display:none" not in style:
            return True
    return False
