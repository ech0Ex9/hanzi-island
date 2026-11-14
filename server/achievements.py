"""小岛成就：从真实学习记录推导，不引入积分货币。

每枚印章只解锁一次；进度实时计算。解锁记录在 `badge_unlocks`，
首次对有历史数据的库初始化时静默补录，避免一次弹很多旧成就。
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterable

from .db import get_settings, now_iso, today_str
from .srs import longest_streak

CATEGORY_ORDER = ("起步", "坚持", "识字", "勇气", "探索")

# id, category, title, description, seal, value_key, target
BADGES: tuple[tuple[str, str, str, str, str, str, int], ...] = (
    (
        "first_session",
        "起步",
        "初次上岸",
        "完成第一组今日学习",
        "岸",
        "completed_sessions",
        1,
    ),
    (
        "first_recognition",
        "起步",
        "第一次点名",
        "完成第一次认字自评",
        "名",
        "recognition_reported",
        1,
    ),
    (
        "first_review",
        "起步",
        "第一次回来",
        "第一次复习学过的字",
        "回",
        "review_count",
        1,
    ),
    (
        "streak_3",
        "坚持",
        "三日小火苗",
        "连续学习 3 天",
        "火",
        "longest_streak",
        3,
    ),
    (
        "streak_7",
        "坚持",
        "七日灯塔",
        "连续学习 7 天",
        "灯",
        "longest_streak",
        7,
    ),
    (
        "streak_30",
        "坚持",
        "三十日环岛",
        "连续学习 30 天",
        "岛",
        "longest_streak",
        30,
    ),
    (
        "learned_10",
        "识字",
        "小岛居民",
        "学过 10 个课内字",
        "居",
        "learned",
        10,
    ),
    (
        "learned_50",
        "识字",
        "点灯人",
        "学过 50 个课内字",
        "光",
        "learned",
        50,
    ),
    (
        "learned_100",
        "识字",
        "小船长",
        "学过 100 个课内字",
        "船",
        "learned",
        100,
    ),
    (
        "learned_300",
        "识字",
        "岛上园丁",
        "学过 300 个课内字",
        "园",
        "learned",
        300,
    ),
    (
        "learned_688",
        "识字",
        "灯塔守护者",
        "学完 688 个课内字",
        "塔",
        "learned",
        688,
    ),
    (
        "brave_unknown",
        "勇气",
        "勇敢星",
        "自评「不认识」的字，复习时答对了",
        "勇",
        "brave_unknown",
        1,
    ),
    (
        "fix_overconfident",
        "勇气",
        "补洞小能手",
        "自评「认识」但答错的字，后来复习答对了",
        "补",
        "fixed_overconfident",
        1,
    ),
    (
        "three_types",
        "探索",
        "三题全能",
        "听音、填空、拼音三种题型都答过",
        "题",
        "question_types",
        3,
    ),
    (
        "radical_collector",
        "探索",
        "部首收藏家",
        "10 个部首，每个至少 3 个学过的字",
        "部",
        "radicals",
        10,
    ),
)

BADGE_IDS = {badge[0] for badge in BADGES}
BADGE_ORDER = {badge[0]: index for index, badge in enumerate(BADGES)}


def _scalar(conn: sqlite3.Connection, sql: str) -> int:
    row = conn.execute(sql).fetchone()
    return int(row[0]) if row else 0


def _values(conn: sqlite3.Connection) -> dict[str, int]:
    """一次性算出所有成就的当前值，避免每个印章都查一遍库。"""
    return {
        "completed_sessions": _scalar(
            conn,
            "SELECT COUNT(*) FROM sessions WHERE completed = 1",
        ),
        "recognition_reported": _scalar(
            conn, "SELECT COUNT(*) FROM recognition_items"
        ),
        "review_count": _scalar(
            conn,
            """
            SELECT (SELECT COUNT(*) FROM char_progress WHERE attempts >= 2)
                 + (SELECT COUNT(*) FROM recognition_items WHERE attempts >= 1)
            """,
        ),
        "longest_streak": longest_streak(conn),
        "learned": _scalar(
            conn,
            """
            SELECT COUNT(*) FROM char_progress p
            WHERE p.first_seen_at IS NOT NULL
              AND EXISTS (SELECT 1 FROM curriculum_items i WHERE i.char = p.char)
            """,
        ),
        "brave_unknown": _scalar(
            conn,
            """
            SELECT COUNT(*) FROM recognition_items
            WHERE self_report = 'unknown'
              AND attempts > 0
              AND (first_quiz_correct = 1 OR last_result = 1)
            """,
        ),
        "fixed_overconfident": _scalar(
            conn,
            """
            SELECT COUNT(*) FROM recognition_items
            WHERE self_report = 'known'
              AND first_quiz_correct = 0
              AND last_result = 1
            """,
        ),
        "question_types": _scalar(
            conn, "SELECT COUNT(DISTINCT question_type) FROM attempts"
        ),
        "radicals": _scalar(
            conn,
            """
            SELECT COUNT(*) FROM (
              SELECT c.radical
              FROM char_progress p
              JOIN characters c ON c.char = p.char
              WHERE p.first_seen_at IS NOT NULL
                AND TRIM(COALESCE(c.radical, '')) != ''
              GROUP BY c.radical
              HAVING COUNT(*) >= 3
            )
            """,
        ),
    }


def _has_learning_history(conn: sqlite3.Connection) -> bool:
    return bool(
        _scalar(conn, "SELECT COUNT(*) FROM attempts")
        or _scalar(conn, "SELECT COUNT(*) FROM recognition_items")
        or _scalar(
            conn,
            "SELECT COUNT(*) FROM char_progress WHERE first_seen_at IS NOT NULL",
        )
    )


def _achievements_initialized(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT value_json FROM settings WHERE key = 'achievements_initialized'"
    ).fetchone()
    if row is None:
        return False
    try:
        return bool(json.loads(row["value_json"]))
    except (TypeError, json.JSONDecodeError):
        return False


def _sync(conn: sqlite3.Connection) -> dict[str, int]:
    """把新达成的成就写入流水；首次对旧数据初始化时静默补录。"""
    values = _values(conn)
    initialized = _achievements_initialized(conn)
    # 旧库第一次启用：已经达成的成就直接标记为已看，避免一次弹十几个旧印章。
    silent_backfill = not initialized and _has_learning_history(conn)
    ts = now_iso()
    local_date = today_str()

    for badge_id, _category, _title, _description, _seal, value_key, target in BADGES:
        if values.get(value_key, 0) < target:
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO badge_unlocks(
              badge_id, unlocked_at, local_date, seen, meta_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                badge_id,
                ts,
                local_date,
                1 if silent_backfill else 0,
                json.dumps({"value": values.get(value_key, 0)}, ensure_ascii=False),
            ),
        )
    if not initialized:
        conn.execute(
            "UPDATE settings SET value_json = ?, updated_at = ? "
            "WHERE key = 'achievements_initialized'",
            (json.dumps(True), now_iso()),
        )
    conn.commit()
    return values


def _badge_dict(
    badge: tuple[str, str, str, str, str, str, int],
    values: dict[str, int],
    unlock: sqlite3.Row | None,
) -> dict[str, Any]:
    badge_id, category, title, description, seal, value_key, target = badge
    value = int(values.get(value_key, 0))
    earned = unlock is not None or value >= target
    return {
        "id": badge_id,
        "category": category,
        "title": title,
        "description": description,
        "seal": seal,
        "target": target,
        "value": value,
        "progress": min(value, target),
        "earned": earned,
        "unlocked_at": unlock["unlocked_at"] if unlock else None,
        "seen": bool(unlock["seen"]) if unlock else False,
    }


def summary(conn: sqlite3.Connection) -> dict[str, Any]:
    values = _sync(conn)
    unlocks = {
        row["badge_id"]: row
        for row in conn.execute("SELECT * FROM badge_unlocks").fetchall()
    }
    badges = [
        _badge_dict(badge, values, unlocks.get(badge[0])) for badge in BADGES
    ]
    earned = [badge for badge in badges if badge["earned"]]
    unseen = [badge for badge in earned if not badge["seen"]]
    next_badges = sorted(
        [badge for badge in badges if not badge["earned"]],
        key=lambda badge: (
            badge["target"] - badge["progress"],
            CATEGORY_ORDER.index(badge["category"]),
            BADGE_ORDER.get(badge["id"], 999),
        ),
    )[:3]
    recent = sorted(
        earned,
        key=lambda badge: badge["unlocked_at"] or "",
        reverse=True,
    )[:3]
    settings = get_settings(conn)
    return {
        "enabled": settings.get("achievements_enabled", True) is not False,
        "earned": len(earned),
        "total": len(badges),
        "badges": badges,
        "next": next_badges,
        "unseen": unseen,
        "recent": recent,
    }


def mark_seen(conn: sqlite3.Connection, ids: Iterable[str] | None = None) -> dict[str, Any]:
    """标记成就为已展示；不传 ids 时清空所有未读。"""
    selected = [badge_id for badge_id in (ids or []) if badge_id in BADGE_IDS]
    if selected:
        placeholders = ",".join("?" for _ in selected)
        conn.execute(
            f"UPDATE badge_unlocks SET seen = 1 WHERE badge_id IN ({placeholders})",
            selected,
        )
    else:
        conn.execute("UPDATE badge_unlocks SET seen = 1 WHERE seen = 0")
    conn.commit()
    return summary(conn)
