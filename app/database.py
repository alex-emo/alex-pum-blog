"""数据库引擎与会话管理。SQLite 部署在单机 1G 内存上够用，开 WAL 提升并发读。"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

# check_same_thread=False：FastAPI 的线程池里会跨线程复用连接
# timeout=15：写锁冲突时最多等 15 秒，避免 SQLite 直接抛 database is locked
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False, "timeout": 15},
    pool_pre_ping=True,
    future=True,
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    """每条物理连接建立时设置 PRAGMA。"""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")    # 读写不互斥
        cursor.execute("PRAGMA synchronous=NORMAL")  # WAL 下的安全/性能平衡点
        cursor.execute("PRAGMA foreign_keys=ON")     # SQLite 默认不启用外键约束
        cursor.execute("PRAGMA busy_timeout=15000")
    finally:
        cursor.close()


SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, expire_on_commit=False
)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：每个请求一个会话，请求结束自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
