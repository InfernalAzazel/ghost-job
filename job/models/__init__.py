"""本地 SQLite：路径、引擎、初始化。"""

from __future__ import annotations

import importlib
from pathlib import Path

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

    for mod in ("job.models.job", "job.models.search", "job.models.setting"):
        importlib.import_module(mod)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(
        f"sqlite:///{DB_PATH}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(_engine)
    return _engine


def db_session() -> Session:
    """短生命周期 Session（`with db_session() as s:`）。"""
    return Session(get_engine())


def init_db() -> None:
    """建表，并确保有求职配置。"""
    from job.models.search import SearchConfigRow

    SearchConfigRow.ensure()
