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
