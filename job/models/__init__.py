"""本地 SQLite：路径、引擎、初始化。"""

from __future__ import annotations

import importlib
from pathlib import Path

from sqlalchemy import inspect, text
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


def _column_sql(column, engine) -> str:
    """补列用的列定义：类型 + 默认值。

    SQLite 给已有表加 ``NOT NULL`` 列必须带默认值，所以模型的默认值要一起带上；
    拿不到可用默认值（例如 ``default_factory``）时退化成可空列——写入时仍由
    Python 侧的默认值兜底。
    """
    ddl = f'"{column.name}" {column.type.compile(engine.dialect)}'
    default = getattr(column.default, "arg", None)
    if isinstance(default, str):
        return f"{ddl} NOT NULL DEFAULT '{default.replace(chr(39), chr(39) * 2)}'"
    if isinstance(default, bool):
        return f"{ddl} NOT NULL DEFAULT {int(default)}"
    if isinstance(default, (int, float)):
        return f"{ddl} NOT NULL DEFAULT {default}"
    return ddl


def _add_missing_columns(engine) -> None:
    """给已存在的表补上模型里新增的列。

    ``create_all`` 只建缺失的表，**不会**给已有表加列；老库直接跑新版本会报
    ``no such column``，所以这里按模型定义幂等地补齐。
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            have = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in have:
                    continue
                conn.execute(
                    text(
                        f"ALTER TABLE {table.name} ADD COLUMN {_column_sql(column, engine)}"
                    )
                )


def get_engine():
    """懒加载引擎；首次调用时建库建表并补齐新增的列。"""
    global _engine
    if _engine is not None:
        return _engine

    for mod in (
        "job.models.job",
        "job.models.search",
        "job.models.setting",
        "job.models.chat",
        "job.models.company",
    ):
        importlib.import_module(mod)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(
        f"sqlite:///{DB_PATH}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(_engine)
    _add_missing_columns(_engine)
    return _engine


def db_session() -> Session:
    """短生命周期 Session（`with db_session() as s:`）。"""
    return Session(get_engine())


def init_db() -> None:
    """建表，并确保有求职配置。"""
    from job.models.search import SearchConfigRow

    SearchConfigRow.ensure()
