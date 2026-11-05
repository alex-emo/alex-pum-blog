"""运维小工具：迁移数据库、管理管理员账号、导出代码高亮 CSS。

用法：
    python -m scripts.manage migrate
    python -m scripts.manage create-admin admin
    python -m scripts.manage reset-password admin
    python -m scripts.manage export-css app/static/code.css
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

# 允许从项目根目录执行 python -m scripts.manage
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app import models  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app.markdown_render import pygments_css, render_with_toc  # noqa: E402
from app.migrations.runner import upgrade_all  # noqa: E402
from app.security import hash_password  # noqa: E402


def cmd_migrate(_args: argparse.Namespace) -> None:
    executed = upgrade_all(engine)
    if executed:
        print("已执行迁移:", ", ".join(executed))
    else:
        print("数据库已是最新版本")


def _read_password(args: argparse.Namespace) -> str:
    password = getattr(args, "password", None)
    if password:
        return password
    first = getpass.getpass("密码: ")
    second = getpass.getpass("再输一次: ")
    if first != second:
        raise SystemExit("两次输入不一致")
    if len(first) < 8:
        raise SystemExit("密码至少 8 位")
    return first


def cmd_rerender(_args: argparse.Namespace) -> None:
    """用当前 Markdown 管线重新渲染所有文章存库（改扩展后需要跑一次）。"""
    from sqlalchemy import func

    from app.models import Post

    with SessionLocal() as db:
        posts = db.execute(select(Post)).scalars().all()
        for post in posts:
            html, toc = render_with_toc(post.content_md)
            post.content_html = html
            post.content_toc = toc
        db.commit()
        total = db.execute(select(func.count(Post.id))).scalar_one()
    print(f"已重新渲染 {total} 篇文章")


def cmd_create_admin(args: argparse.Namespace) -> None:
    password = _read_password(args)
    with SessionLocal() as db:
        exists = db.execute(
            select(models.AdminUser).where(models.AdminUser.username == args.username)
        ).scalar_one_or_none()
        if exists:
            raise SystemExit(f"用户 {args.username} 已存在，用 reset-password 改密码")
        db.add(models.AdminUser(username=args.username, password_hash=hash_password(password)))
        db.commit()
    print(f"已创建管理员 {args.username}")


def cmd_reset_password(args: argparse.Namespace) -> None:
    password = _read_password(args)
    with SessionLocal() as db:
        user = db.execute(
            select(models.AdminUser).where(models.AdminUser.username == args.username)
        ).scalar_one_or_none()
        if user is None:
            raise SystemExit(f"用户 {args.username} 不存在")
        user.password_hash = hash_password(password)
        db.commit()
    print(f"已重置 {args.username} 的密码")


def cmd_export_css(args: argparse.Namespace) -> None:
    target = Path(args.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(pygments_css(args.style, args.dark_style), encoding="utf-8")
    print(f"代码高亮 CSS 已写入 {target}")


def main() -> None:
    parser = argparse.ArgumentParser(description="博客运维工具")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("migrate", help="执行数据库迁移").set_defaults(func=cmd_migrate)

    sub.add_parser("rerender", help="重新渲染所有文章的 HTML").set_defaults(func=cmd_rerender)

    p_create = sub.add_parser("create-admin", help="创建管理员")
    p_create.add_argument("username")
    p_create.add_argument("--password", help="不传则交互式输入")
    p_create.set_defaults(func=cmd_create_admin)

    p_reset = sub.add_parser("reset-password", help="重置管理员密码")
    p_reset.add_argument("username")
    p_reset.add_argument("--password", help="不传则交互式输入")
    p_reset.set_defaults(func=cmd_reset_password)

    p_css = sub.add_parser("export-css", help="导出代码高亮 CSS")
    p_css.add_argument("path")
    p_css.add_argument("--style", default="friendly")
    p_css.add_argument("--dark-style", default="one-dark")
    p_css.set_defaults(func=cmd_export_css)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
