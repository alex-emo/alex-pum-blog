"""数据库 + 媒体文件备份，配合 systemd timer 每天跑一次。

用法：
    venv/bin/python -m scripts.backup --keep 14
备份写到 backups/，按时间戳命名，超过保留天数的自动清理。
"""
from __future__ import annotations

import argparse
import sqlite3
import tarfile
import time
from pathlib import Path

from app.config import BASE_DIR, settings


def sqlite_path() -> Path:
    url = settings.database_url
    if not url.startswith("sqlite:///"):
        raise SystemExit(f"只支持 SQLite 备份，当前 DATABASE_URL={url}")
    return Path(url[len("sqlite:///"):])


def backup_database(target: Path) -> None:
    source = sqlite_path()
    if not source.exists():
        raise SystemExit(f"数据库不存在: {source}")
    # sqlite3 的在线备份 API：WAL 模式下也能得到一致快照
    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as src, sqlite3.connect(target) as dst:
        src.backup(dst)


def backup_media(target: Path) -> None:
    if not settings.media_dir.exists():
        return
    with tarfile.open(target, "w:gz") as tar:
        tar.add(settings.media_dir, arcname="media")


def prune(directory: Path, keep_days: int) -> list[Path]:
    cutoff = time.time() - keep_days * 86400
    removed = []
    for path in directory.glob("blog-*.db*"):
        if path.stat().st_mtime < cutoff:
            path.unlink()
            removed.append(path)
    for path in directory.glob("media-*.tar.gz"):
        if path.stat().st_mtime < cutoff:
            path.unlink()
            removed.append(path)
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description="备份博客数据库与图片")
    parser.add_argument("--dir", default=str(BASE_DIR / "backups"), help="备份目录")
    parser.add_argument("--keep", type=int, default=14, help="保留天数")
    parser.add_argument("--skip-media", action="store_true", help="只备份数据库")
    args = parser.parse_args()

    directory = Path(args.dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")

    db_target = directory / f"blog-{stamp}.db"
    backup_database(db_target)
    print(f"数据库 -> {db_target}")

    if not args.skip_media:
        media_target = directory / f"media-{stamp}.tar.gz"
        backup_media(media_target)
        if media_target.exists():
            print(f"媒体   -> {media_target}")

    for path in prune(directory, args.keep):
        print(f"清理旧备份 {path}")


if __name__ == "__main__":
    main()
