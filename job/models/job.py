"""职位表模型与增删查改。"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

from sqlalchemy import or_
from sqlmodel import Field, SQLModel, col, select

if TYPE_CHECKING:
    from job.boss.jobs import Job


def _now() -> datetime:
    return datetime.now(UTC)


def _csv_cell(value: Any) -> Any:
    """CSV 单元格：布尔转是/否，时间转本地时间，空值留空。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, datetime):
        local = value.replace(tzinfo=value.tzinfo or UTC).astimezone()
        return local.strftime("%Y-%m-%d %H:%M:%S")
    return value


class JobRow(SQLModel, table=True):
    """看过的岗位：合适的投递，不合适的也记下原因，下次遇到直接跳过。"""

    __tablename__ = "job"

    # 高匹配分数线
    HIGH_MATCH: ClassVar[int] = 80
    # 分析状态筛选项（第一项为不筛选）
    ANALYSIS_FILTERS: ClassVar[tuple[str, ...]] = (
        "全部分析状态",
        "已分析",
        "未分析",
        f"高匹配（≥{HIGH_MATCH}）",
    )
    # 是否合适筛选项（第一项为不筛选）
    SUITABLE_FILTERS: ClassVar[tuple[str, ...]] = ("全部", "合适", "不合适")
    # 导出 CSV 的列：表字段 -> 表头；须覆盖全部表字段
    CSV_COLUMNS: ClassVar[dict[str, str]] = {
        "uid": "主键",
        "job_id": "职位 ID",
        "title": "岗位名称",
        "company": "公司",
        "salary": "薪资",
        "location": "地点",
        "experience": "经验",
        "education": "学历",
        "suitable": "是否合适",
        "applied": "是否已投递",
        "reason": "判断描述",
        "match_score": "匹配度",
        "hr_name": "HR",
        "hr_title": "HR 职位",
        "address": "工作地址",
        "link": "岗位链接",
        "description": "职位描述",
        "created_at": "入库时间",
        "updated_at": "更新时间",
    }

    uid: str = Field(primary_key=True, description="主键：优先 job_id，否则用 link")
    job_id: str | None = Field(default=None, index=True)
    link: str = Field(default="", index=True)
    title: str = ""
    salary: str = ""
    company: str = ""
    location: str = ""
    experience: str = ""
    education: str = ""
    description: str = ""
    hr_name: str = ""
    hr_title: str = ""
    address: str = ""
    match_score: int | None = Field(
        default=None, index=True, description="匹配度 0–100；未分析为空"
    )
    suitable: bool = Field(default=True, description="是否合适")
    applied: bool = Field(default=False, description="是否已投递（点过「立即沟通」）")
    reason: str = Field(default="", description="合适或不合适的原因，如「外包公司」")
    created_at: datetime = Field(default_factory=_now, index=True, description="首次入库时间（UTC）")
    updated_at: datetime = Field(default_factory=_now, description="最后更新时间（UTC）")

    @property
    def result(self) -> str:
        """处理结果：已投递 / 已沟通过 / 不合适。"""
        if not self.suitable:
            return "不合适"
        return "已投递" if self.applied else "已沟通过"

    def to_dict(self) -> dict[str, Any]:
        """转为前端表格字典。"""
        score = self.match_score
        created = self.created_at.replace(tzinfo=self.created_at.tzinfo or UTC)
        return {
            "uid": self.uid,
            "title": self.title,
            "salary": self.salary,
            "company": self.company,
            "location": self.location,
            "link": self.link,
            "hrName": self.hr_name,
            "hrTitle": self.hr_title,
            "address": self.address,
            "description": self.description,
            "experience": self.experience,
            "education": self.education,
            "matchStatus": "未分析" if score is None else f"{score} 分",
            "matchHigh": score is not None and score >= self.HIGH_MATCH,
            "result": self.result,
            "suitable": self.suitable,
            "reason": self.reason,
            "createdAt": created.astimezone().strftime("%Y-%m-%d %H:%M"),
        }

    @staticmethod
    def uid_for(job: Job) -> str:
        """根据抓取结果生成稳定主键。"""
        return job.job_id or job.link or f"{job.company}|{job.title}|{job.salary}"

    @classmethod
    def record(
        cls,
        job: Job,
        *,
        suitable: bool = True,
        reason: str = "",
        score: int | None = None,
        applied: bool = False,
    ) -> JobRow:
        """按 uid 插入或更新判断结果；没给新匹配度 ``score`` 时保留已有的。"""
        from job.models import db_session

        row = cls(
            **job.model_dump(),
            uid=cls.uid_for(job),
            match_score=score,
            suitable=suitable,
            applied=applied,
            reason=reason,
        )
        with db_session() as session:
            if existing := session.get(cls, row.uid):
                row.created_at = existing.created_at
                if score is None:
                    row.match_score = existing.match_score
            merged = session.merge(row)
            session.commit()
            session.refresh(merged)
            return merged

    @classmethod
    def find_duplicate(cls, job: Job) -> JobRow | None:
        """库里的同一岗位：职位 ID 相同，或招聘标题、公司、HR 都相同。"""
        from job.models import db_session

        with db_session() as session:
            if row := session.get(cls, cls.uid_for(job)):
                return row
            stmt = select(cls).where(
                col(cls.title) == job.title,
                col(cls.company) == job.company,
                col(cls.hr_name) == job.hr_name,
            )
            return session.exec(stmt.limit(1)).first()

    @classmethod
    def _apply_filters(cls, stmt, search: str, analysis: str, suitable: str):
        """按岗位名 / 公司模糊搜，并按分析状态、是否合适筛选。"""
        if q := search.strip():
            like = f"%{q}%"
            stmt = stmt.where(
                or_(col(cls.title).like(like), col(cls.company).like(like))
            )
        _, analyzed, pending, high = cls.ANALYSIS_FILTERS
        score = col(cls.match_score)
        conditions = {
            analyzed: score.is_not(None),
            pending: score.is_(None),
            high: score >= cls.HIGH_MATCH,
        }
        if analysis in conditions:
            stmt = stmt.where(conditions[analysis])
        _, yes, no = cls.SUITABLE_FILTERS
        if suitable in (yes, no):
            stmt = stmt.where(col(cls.suitable).is_(suitable == yes))
        return stmt

    @classmethod
    def count(cls, *, search: str = "", analysis: str = "", suitable: str = "") -> int:
        """统计岗位数；可按关键字、分析状态与是否合适筛选。"""
        from sqlalchemy import func

        from job.models import db_session

        with db_session() as session:
            stmt = select(func.count()).select_from(cls)
            stmt = cls._apply_filters(stmt, search, analysis, suitable)
            return int(session.exec(stmt).one())

    @classmethod
    def count_applied(cls) -> int:
        """累计投递数。"""
        from sqlalchemy import func

        from job.models import db_session

        stmt = select(func.count()).select_from(cls).where(col(cls.applied).is_(True))
        with db_session() as session:
            return int(session.exec(stmt).one())

    @classmethod
    def list_dicts(
        cls,
        *,
        search: str = "",
        analysis: str = "",
        suitable: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """分页列表（新入库优先）。"""
        from job.models import db_session

        with db_session() as session:
            stmt = select(cls).order_by(col(cls.created_at).desc())
            stmt = cls._apply_filters(stmt, search, analysis, suitable)
            rows = session.exec(stmt.offset(offset).limit(limit)).all()
        return [r.to_dict() for r in rows]

    @classmethod
    def to_csv(cls, uids: list[str] | None = None) -> tuple[str, int]:
        """导出 CSV 文本与条数：``uids`` 为空导出全部，否则只导出这些岗位（新入库优先）。

        文本带 UTF-8 BOM，Excel 直接打开中文不乱码。
        """
        from job.models import db_session

        stmt = select(cls).order_by(col(cls.created_at).desc())
        if uids:
            stmt = stmt.where(col(cls.uid).in_(uids))
        with db_session() as session:
            rows = session.exec(stmt).all()
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(cls.CSV_COLUMNS.values())
        for row in rows:
            writer.writerow(_csv_cell(getattr(row, key)) for key in cls.CSV_COLUMNS)
        return "\ufeff" + buffer.getvalue(), len(rows)

    @classmethod
    def get_dict(cls, uid: str) -> dict[str, Any] | None:
        """按主键查询。"""
        from job.models import db_session

        with db_session() as session:
            row = session.get(cls, uid)
            return None if row is None else row.to_dict()

    @classmethod
    def count_today(cls) -> int:
        """今天（本地时区）投递的岗位数。"""
        from sqlalchemy import func

        from job.models import db_session

        midnight = datetime.now().astimezone().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        since = midnight.astimezone(UTC)
        stmt = (
            select(func.count())
            .select_from(cls)
            .where(col(cls.applied).is_(True), col(cls.created_at) >= since)
        )
        with db_session() as session:
            return int(session.exec(stmt).one())

    @classmethod
    def set_verdict(
        cls, uid: str, *, suitable: bool, reason: str, score: int | None
    ) -> bool:
        """写回 AI 判断：是否合适、原因与匹配度（为空时保留原匹配度）；岗位不存在返回 False。"""
        from job.models import db_session

        with db_session() as session:
            row = session.get(cls, uid)
            if row is None:
                return False
            row.suitable = suitable
            row.reason = reason
            if score is not None:
                row.match_score = score
            row.updated_at = _now()
            session.add(row)
            session.commit()
            return True

    @classmethod
    def delete_by_uid(cls, uid: str) -> bool:
        """删除一条，不存在则 False。"""
        from job.models import db_session

        with db_session() as session:
            row = session.get(cls, uid)
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True

    @classmethod
    def delete_many(cls, uids: list[str]) -> int:
        """批量删除，返回实际删除数。"""
        from job.models import db_session

        deleted = 0
        with db_session() as session:
            for uid in uids:
                row = session.get(cls, uid)
                if row is None:
                    continue
                session.delete(row)
                deleted += 1
            session.commit()
        return deleted
