#!/usr/bin/env python3
"""校验艾宾浩斯认字模块：范围字数、间隔阶梯、升降级边界。

用法：python3 tools/validate_recognition.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server import recognition  # noqa: E402
from server.db import get_db  # noqa: E402

EXPECTED_SCOPES = {"literacy": 1300, "all": 688, "1a": 279, "1b": 413}
EXPECTED_INTERVALS = {0: 0, 1: 1, 2: 2, 3: 4, 4: 7, 5: 15, 6: 30, 7: 60}


def main() -> int:
    errors: list[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    check(
        recognition.RECOGNITION_INTERVAL_DAYS == EXPECTED_INTERVALS,
        "复习间隔不是 0/1/2/4/7/15/30/60 天",
    )
    check(recognition.MAX_REVIEWS_PER_SESSION == 15, "每日复习上限应为 15")

    # 纯排程边界
    check(
        recognition.due_date_for_stage(0, date(2026, 1, 1)) == "2026-01-01",
        "R0 应在当天复习",
    )
    check(
        recognition.due_date_for_stage(1, date(2026, 1, 1)) == "2026-01-02",
        "R1 应在次日复习",
    )
    check(
        recognition.due_date_for_stage(7, date(2026, 1, 1)) == "2026-03-02",
        "R7 应在 60 天后复习",
    )
    check(
        recognition._plain_pinyin("kuài") == "kuai",
        "拼音搜索应能忽略声调",
    )

    cases = [
        ("认识的第一次答对", ("known", 1, 0, 0, True), (2, 1)),
        ("认识的第二次答对", ("known", 2, 1, 1, True), (3, 2)),
        ("连续两次后进入 R4", ("known", 3, 2, 2, True), (4, 3)),
        ("不认识第一次答对跳一级", ("unknown", 0, 0, 0, True), (2, 1)),
        ("不认识后续答对只升一级", ("unknown", 2, 0, 2, True), (3, 1)),
        ("答错降一级", ("known", 4, 3, 5, False), (3, 0)),
        ("连续不足 2 次不能进 R4", ("known", 3, 0, 5, True), (3, 1)),
        ("R0 答错仍是 R0", ("unknown", 0, 0, 1, False), (0, 0)),
        ("R7 答对保持 R7", ("known", 7, 5, 5, True), (7, 6)),
        ("R7 答错降到 R6", ("known", 7, 5, 5, False), (6, 0)),
    ]
    for label, args, expected in cases:
        actual = recognition.stage_after_attempt(*args)
        check(actual == expected, f"{label}：期望 {expected}，实际 {actual}")

    # 范围和数据库表
    with get_db() as conn:
        scope_sets: dict[str, set[str]] = {}
        for scope, expected_total in EXPECTED_SCOPES.items():
            chars = recognition._scope_chars(conn, scope)
            scope_sets[scope] = {item["char"] for item in chars}
            check(len(chars) == expected_total, f"范围 {scope} 应有 {expected_total} 字，实际 {len(chars)}")
            unique = {item["char"] for item in chars}
            check(len(unique) == len(chars), f"范围 {scope} 有重复字")
        check(
            len(scope_sets["1a"] | scope_sets["1b"]) == 688,
            "上册 + 下册去重后应为 688 字",
        )
        check(
            len(scope_sets["1a"] & scope_sets["1b"]) == 4,
            "上册和下册应有 4 个跨册重复字",
        )
        check(
            scope_sets["all"] == (scope_sets["1a"] | scope_sets["1b"]),
            "全部课内应等于上册 + 下册去重",
        )
        check(
            len(scope_sets["literacy"] & scope_sets["all"]) == 664,
            "幼儿识字 1300 中应包含 664 个课内字",
        )
        check(
            len(scope_sets["literacy"] - scope_sets["all"]) == 636,
            "幼儿识字 1300 应新增 636 个拓展字",
        )
        missing_content = conn.execute(
            """
            SELECT l.char FROM literacy_entries l
            LEFT JOIN characters c ON c.char = l.char
            WHERE c.char IS NULL
            """
        ).fetchall()
        check(not missing_content, f"幼儿识字表有 {len(missing_content)} 个字缺少内容")
        for table in ("recognition_runs", "recognition_items", "recognition_attempts", "literacy_entries"):
            try:
                conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
            except Exception as error:  # noqa: BLE001
                errors.append(f"缺少数据表 {table}：{error}")

    print(f"艾宾浩斯认字：范围 {len(EXPECTED_SCOPES)} 个，排程用例 {len(cases)} 个，错误 {len(errors)} 个")
    for line in errors:
        print("  [错误]", line)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
