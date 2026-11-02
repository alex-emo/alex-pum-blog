"""轻量迁移：按版本号顺序执行，记录在 schema_version 表里。

不引入 alembic —— 单机 SQLite 博客用不着那么重的工具链，
每个迁移就是一个模块，暴露 VERSION 和 upgrade(conn)。
"""
from __future__ import annotations

import importlib
import pkgutil
import re
from datetime import datetime, timezone

from sqlalchemy import Connection, text

from app.migrations import __name__ as _pkg

VERSION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""


def _ensure_version_table(conn: Connection) -> None:
    conn.execute(text(VERSION_TABLE_SQL))


def _applied_versions(conn: Connection) -> set[int]:
    rows = conn.execute(text("SELECT version FROM schema_version")).all()
    return {row[0] for row in rows}


def _discover() -> list:
    """找出所有 mXXXX_*.py 模块，按 VERSION 排序。"""
    modules = []
    package = importlib.import_module(_pkg)
    for info in pkgutil.iter_modules(package.__path__):
        if not re.match(r"^m\d{4}_", info.name):
            continue
        module = importlib.import_module(f"{_pkg}.{info.name}")
        modules.append(module)
    modules.sort(key=lambda m: m.VERSION)
    return modules


def upgrade_all(bind) -> list[str]:
    """执行所有未应用的迁移，返回执行记录（给启动日志用）。"""
    executed: list[str] = []
    with bind.begin() as conn:
        _ensure_version_table(conn)
        applied = _applied_versions(conn)

    for module in _discover():
        if module.VERSION in applied:
            continue
        # 每个迁移一个事务，失败则整体回滚、后面的不再执行
        with bind.begin() as conn:
            module.upgrade(conn)
            conn.execute(
                text(
                    "INSERT INTO schema_version (version, name, applied_at) "
                    "VALUES (:v, :n, :t)"
                ),
                {
                    "v": module.VERSION,
                    "n": module.__name__.rsplit(".", 1)[-1],
                    "t": datetime.now(timezone.utc).isoformat(),
                },
            )
        executed.append(module.__name__.rsplit(".", 1)[-1])
    return executed
