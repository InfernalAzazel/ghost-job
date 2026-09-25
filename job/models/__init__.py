"""本地 SQLite：路径、引擎、初始化。"""

from __future__ import annotations

import importlib
from pathlib import Path

from sqlalchemy import Engine, inspect, text
from sqlalchemy.schema import CreateColumn
from sqlmodel import Session, SQLModel, create_engine

DATA_DIR = Path.home() / ".ghost-job"
DB_PATH = DATA_DIR / "ghost-job.db"
_engine = None


def reset_engine() -> None:
    """测试用：释放并清空引擎缓存。"""
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None


def get_engine():
    """懒加载引擎；首次调用时建库建表。"""
    global _engine
    if _engine is not None:
        return _engine

    for mod in ("job.models.job", "job.models.plan"):
        importlib.import_module(mod)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(
        f"sqlite:///{DB_PATH}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(_engine)
    _add_missing_columns(_engine)
    return _engine


def _add_missing_columns(engine: Engine) -> None:
    """老库补列：模型新增的字段按 ``ALTER TABLE ADD COLUMN`` 追加。"""
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name not in existing:
                    ddl = CreateColumn(column).compile(engine)
                    conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {ddl}"))


def db_session() -> Session:
    """短生命周期 Session（`with db_session() as s:`）。"""
    return Session(get_engine())


def init_db() -> None:
    """建表，并确保有默认求职方案。"""
    from job.models.plan import SearchPlanRow

    get_engine()
    SearchPlanRow.ensure_default()
