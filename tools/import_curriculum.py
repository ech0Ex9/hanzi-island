#!/usr/bin/env python3
"""把 data/curriculum/*.csv 导入数据库（books / units / lessons / curriculum_items）。

用法：
    python3 tools/import_curriculum.py          # 导入并回填 characters 旧字段
    python3 tools/import_curriculum.py --dry    # 只统计，不写库

服务启动时也会自动幂等导入；CSV 改了重启即可。本工具用于手动导入和检查。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.curriculum import BOOK_META, CSV_COLUMNS, load_curriculum_csv  # noqa: E402
from server.db import connect_content, init_db  # noqa: E402
from server import curriculum  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry", action="store_true", help="只统计 CSV，不写数据库")
    args = parser.parse_args()

    curriculum_dir = curriculum.CURRICULUM_DIR
    if not curriculum_dir.exists():
        print(f"找不到目录：{curriculum_dir}")
        return 1

    totals: dict[str, int] = {}
    for path in sorted(curriculum_dir.glob("*.csv")):
        book_id = path.stem
        if book_id not in BOOK_META:
            print(f"[错误] 未知册 {book_id}（BOOK_META 没有它）")
            return 1
        rows = load_curriculum_csv(path)
        missing_cols = [c for c in CSV_COLUMNS if c not in (rows[0] if rows else {})]
        if missing_cols:
            print(f"[错误] {path.name} 缺少列：{', '.join(missing_cols)}")
            return 1
        chars = {row["char"].strip() for row in rows if row.get("char", "").strip()}
        totals[book_id] = len(rows)
        print(f"{path.name}: {len(rows)} 个位置 / {len(chars)} 个不同字")

    if args.dry:
        print("（dry run，未写数据库）")
        return 0

    init_db()  # 确保 schema 和 characters 内容就绪
    conn = connect_content()
    try:
        summary = curriculum.import_curriculum(conn)
        updated = curriculum.backfill_character_lesson_fields(conn)
        conn.commit()
        for book in summary["books"]:
            print(
                f"[导入] {book['book_id']}: {book['units']} 个单元 / {book['items']} 个字位置"
            )
        print(f"[回填] characters 旧课程字段：{updated} 个字")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
