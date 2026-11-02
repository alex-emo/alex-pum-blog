"""时间与时区工具：库里存 naive UTC，输出时转站点时区。"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import settings

SITE_TZ = ZoneInfo(settings.site_timezone)


def to_local(value: datetime | None) -> datetime | None:
    """naive UTC -> 站点本地时间（带 tzinfo）。"""
    if value is None:
        return None
    return value.replace(tzinfo=ZoneInfo("UTC")).astimezone(SITE_TZ)


def format_dt(value: datetime | None, fmt: str = "%Y-%m-%d") -> str:
    local = to_local(value)
    return local.strftime(fmt) if local else ""


def format_dt_full(value: datetime | None) -> str:
    return format_dt(value, "%Y-%m-%d %H:%M")


def isoformat_local(value: datetime | None) -> str:
    local = to_local(value)
    return local.isoformat() if local else ""
