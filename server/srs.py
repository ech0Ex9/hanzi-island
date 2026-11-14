"""间隔重复（Leitner 盒子）和今日学习队列。"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from typing import Any

from .db import now_iso, today_str
from .serializers import char_to_dict, progress_to_dict

# 688 字全部学完后，box 5 若仍按 30 天复习，每天到期量会超过 15 个复习预算；
# 2026-11-12 起把最高盒子的间隔延长到 60 天（只影响之后答对的字）。
BOX_DAYS = {0: 0, 1: 1, 2: 3, 3: 7, 4: 15, 5: 60}
# P0 复习预算：280 字学习高峰约 25 个到期/天，每次会话最多复习 15 个，
# 总预算（复习 + 新字）20 个；没排进本次的留在队列，返回 backlog。
MAX_REVIEWS_PER_SESSION = 15
SESSION_TOTAL_BUDGET = 20


def mastery_for_box(box: int, first_seen_at: str | None) -> str:
    if box <= 0:
        return "learning" if first_seen_at else "new"
    if box <= 2:
        return "learning"
    if box <= 4:
        return "familiar"
    return "mastered"


def apply_attempt(conn: sqlite3.Connection, char: str, is_correct: bool) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM char_progress WHERE char = ?", (char,)
    ).fetchone()
    if row is None:
        raise KeyError(f"未知汉字：{char}")

    box = int(row["box"])
    correct = int(row["correct"])
    wrong = int(row["wrong"])
    streak = int(row["streak"])
    first_seen_at = row["first_seen_at"] or now_iso()

    if is_correct:
        box = min(5, box + 1)
        correct += 1
        streak += 1
    else:
        box = max(0, box - 1)
        wrong += 1
        streak = 0

    due = date.today() + timedelta(days=BOX_DAYS[box])
    due_at = due.isoformat()
    mastery = mastery_for_box(box, first_seen_at)
    ts = now_iso()

    conn.execute(
        """
        UPDATE char_progress SET
          box = ?, due_at = ?, exposures = exposures + 1, attempts = attempts + 1,
          correct = ?, wrong = ?, streak = ?, mastery = ?, first_seen_at = ?,
          last_seen_at = ?, updated_at = ?
        WHERE char = ?
        """,
        (box, due_at, correct, wrong, streak, mastery, first_seen_at, ts, ts, char),
    )
    updated = conn.execute(
        "SELECT * FROM char_progress WHERE char = ?", (char,)
    ).fetchone()
    return progress_to_dict(updated)


def fetch_characters_with_progress(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """characters JOIN char_progress 的行（排序由调用方按课程位置决定）。"""
    return conn.execute(
        """
        SELECT c.*, p.box, p.due_at, p.exposures, p.attempts, p.correct,
               p.wrong, p.streak, p.mastery, p.first_seen_at, p.last_seen_at
        FROM characters c
        JOIN char_progress p ON p.char = c.char
        """
    ).fetchall()


def today_queue(conn: sqlite3.Connection, new_per_day: int) -> dict[str, Any]:
    from . import curriculum

    today = today_str()
    review_rows = conn.execute(
        """
        SELECT c.*, p.box, p.due_at, p.exposures, p.attempts, p.correct,
               p.wrong, p.streak, p.mastery, p.first_seen_at, p.last_seen_at
        FROM char_progress p
        JOIN characters c ON c.char = p.char
        WHERE p.first_seen_at IS NOT NULL
          AND p.due_at IS NOT NULL
          AND p.due_at <= ?
          AND EXISTS (SELECT 1 FROM curriculum_items i WHERE i.char = c.char)
        ORDER BY p.due_at ASC, p.box ASC, p.updated_at ASC
        LIMIT ?
        """,
        (today, MAX_REVIEWS_PER_SESSION),
    ).fetchall()

    due_total = int(
        conn.execute(
            """
            SELECT COUNT(*) FROM char_progress p
            WHERE p.first_seen_at IS NOT NULL AND p.due_at IS NOT NULL AND p.due_at <= ?
              AND EXISTS (SELECT 1 FROM curriculum_items i WHERE i.char = p.char)
            """,
            (today,),
        ).fetchone()[0]
    )
    backlog = max(0, due_total - len(review_rows))

    introduced_today = int(
        conn.execute(
            """
            SELECT COUNT(*) FROM char_progress p
            WHERE substr(p.first_seen_at, 1, 10) = ?
              AND EXISTS (SELECT 1 FROM curriculum_items i WHERE i.char = p.char)
            """,
            (today,),
        ).fetchone()[0]
    )
    remaining_new = max(0, int(new_per_day) - introduced_today)
    remaining_budget = max(0, SESSION_TOTAL_BUDGET - len(review_rows))
    new_limit = min(remaining_new, remaining_budget)

    new_rows = conn.execute(
        """
        SELECT c.*, p.box, p.due_at, p.exposures, p.attempts, p.correct,
               p.wrong, p.streak, p.mastery, p.first_seen_at, p.last_seen_at
        FROM char_progress p
        JOIN characters c ON c.char = p.char
        WHERE p.first_seen_at IS NULL
          AND EXISTS (SELECT 1 FROM curriculum_items i WHERE i.char = c.char)
        """
    ).fetchall()

    # 新字按课程位置（书 → 单元 → 课文 → 字位置）排序。
    positions = curriculum.first_positions(conn)
    fallback_order = int(
        conn.execute("SELECT COALESCE(MAX(item_order), 0) FROM curriculum_items").fetchone()[0]
    ) + 1

    def order_key(row: sqlite3.Row) -> tuple[int, ...]:
        position = positions.get(row["char"])
        if position:
            return curriculum.position_sort_key(position)
        return (99, 99, 999, fallback_order)

    new_rows = sorted(new_rows, key=order_key)
    selected = new_rows[:new_limit]

    # 没有复习时，允许在课文边界多带 1–2 个字：
    # 第一课《天地人》6 个字，默认每天 5 个时也能一次学完；长课文仍按上限拆开。
    LESSON_COMPLETION_SLACK = 2
    if selected and not review_rows and len(selected) < remaining_budget:
        last_lesson = (positions.get(selected[-1]["char"]) or {}).get("lesson_id")
        if last_lesson:
            extra: list[sqlite3.Row] = []
            for row in new_rows[new_limit:]:
                position = positions.get(row["char"]) or {}
                if position.get("lesson_id") != last_lesson:
                    break
                extra.append(row)
                if len(selected) + len(extra) >= remaining_budget:
                    break
            if extra and len(extra) <= LESSON_COMPLETION_SLACK:
                selected = selected + extra

    def with_position(row: sqlite3.Row, mode: str) -> dict[str, Any]:
        data = char_to_dict(row)
        data["mode"] = mode
        position = positions.get(row["char"])
        if position:
            data.update(
                {
                    "book_id": position["book_id"],
                    "book_title": position["book_title"],
                    "unit_id": position["unit_id"],
                    "unit_no": position["unit_no"],
                    "unit_title": position["unit_title"],
                    "lesson_id": position["lesson_id"],
                    "lesson_title": position["lesson_title"],
                    "reading_key": position["reading_key"],
                }
            )
            if position["reading_key"]:
                data["pinyin"] = position["reading_key"]
        return data

    return {
        "reviews": [with_position(row, "review") for row in review_rows],
        "new": [with_position(row, "new") for row in selected],
        "introduced_today": introduced_today,
        "new_limit": int(new_per_day),
        "review_limit": MAX_REVIEWS_PER_SESSION,
        "session_budget": SESSION_TOTAL_BUDGET,
        "backlog": backlog,
    }


def stats_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    today = today_str()
    # 首页统计只算课内 688 字；「幼儿识字 1300」的拓展字不影响课内进度。
    total = int(
        conn.execute("SELECT COUNT(DISTINCT char) FROM curriculum_items").fetchone()[0]
    )
    learned = int(
        conn.execute(
            """
            SELECT COUNT(*) FROM char_progress p
            WHERE p.first_seen_at IS NOT NULL
              AND EXISTS (SELECT 1 FROM curriculum_items i WHERE i.char = p.char)
            """
        ).fetchone()[0]
    )
    mastered = int(
        conn.execute(
            """
            SELECT COUNT(*) FROM char_progress p
            WHERE p.box >= 5
              AND EXISTS (SELECT 1 FROM curriculum_items i WHERE i.char = p.char)
            """
        ).fetchone()[0]
    )
    learning = int(
        conn.execute(
            """
            SELECT COUNT(*) FROM char_progress p
            WHERE p.first_seen_at IS NOT NULL AND p.box < 5
              AND EXISTS (SELECT 1 FROM curriculum_items i WHERE i.char = p.char)
            """
        ).fetchone()[0]
    )
    due = int(
        conn.execute(
            """
            SELECT COUNT(*) FROM char_progress p
            WHERE p.first_seen_at IS NOT NULL AND p.due_at <= ?
              AND EXISTS (SELECT 1 FROM curriculum_items i WHERE i.char = p.char)
            """,
            (today,),
        ).fetchone()[0]
    )

    row = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(is_correct), 0) AS c FROM attempts WHERE local_date = ?",
        (today,),
    ).fetchone()
    today_attempts = int(row["n"])
    today_correct = int(row["c"])
    accuracy = round(today_correct / today_attempts * 100) if today_attempts else 0

    dates = active_dates(conn)
    streak = 0
    cursor = date.today()
    if dates:
        first_day = date.fromisoformat(dates[0])
        if first_day == cursor - timedelta(days=1):
            cursor = cursor - timedelta(days=1)
        for d in dates:
            if date.fromisoformat(d) == cursor:
                streak += 1
                cursor -= timedelta(days=1)
            else:
                break

    return {
        "total": total,
        "learned": learned,
        "mastered": mastered,
        "learning": learning,
        "due": due,
        "today_attempts": today_attempts,
        "today_correct": today_correct,
        "accuracy": accuracy,
        "streak": streak,
    }


def weak_characters(conn: sqlite3.Connection, limit: int = 10) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT c.char, c.pinyin, c.lesson, p.attempts, p.correct, p.wrong,
               p.box, p.mastery, p.last_seen_at
        FROM char_progress p
        JOIN characters c ON c.char = p.char
        WHERE p.attempts > 0
          AND (p.wrong > 0 OR (CAST(p.correct AS REAL) / p.attempts) < 0.8)
        ORDER BY p.wrong DESC,
                 (CAST(p.correct AS REAL) / p.attempts) ASC,
                 p.last_seen_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        {
            "char": r["char"],
            "pinyin": r["pinyin"],
            "lesson": r["lesson"],
            "attempts": r["attempts"],
            "correct": r["correct"],
            "wrong": r["wrong"],
            "box": r["box"],
            "mastery": r["mastery"],
            "last_seen_at": r["last_seen_at"],
        }
        for r in rows
    ]


def list_lessons(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """按课程结构列出课文（实现移到 curriculum.py，保持兼容导出）。"""
    from . import curriculum

    return curriculum.list_lessons(conn)


def list_characters(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """全部有内容的字，按课程位置排序（实现移到 curriculum.py）。"""
    from . import curriculum

    return curriculum.list_characters(conn)


def get_character(conn: sqlite3.Connection, char: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT c.*, p.box, p.due_at, p.exposures, p.attempts, p.correct,
               p.wrong, p.streak, p.mastery, p.first_seen_at, p.last_seen_at
        FROM characters c
        JOIN char_progress p ON p.char = c.char
        WHERE c.char = ?
        """,
        (char,),
    ).fetchone()
    return char_to_dict(row) if row else None


def reset_progress(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM attempts")
    conn.execute("DELETE FROM events")
    conn.execute("DELETE FROM sessions")
    conn.execute("DELETE FROM char_progress")
    # 艾宾浩斯模块也一起清空，避免「清空进度」后还留着旧的自评和复习队列。
    conn.execute("DELETE FROM recognition_attempts")
    conn.execute("DELETE FROM recognition_items")
    conn.execute("DELETE FROM recognition_runs")
    conn.execute("DELETE FROM badge_unlocks")
    conn.execute("INSERT INTO char_progress(char) SELECT char FROM characters")
    conn.commit()


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None


def active_dates(conn: sqlite3.Connection) -> list[str]:
    """普通答题、认字自评和认字复习都算学习日，按日期倒序。"""
    rows = conn.execute(
        """
        SELECT local_date FROM attempts
        UNION
        SELECT local_date FROM recognition_attempts
        UNION
        SELECT substr(reported_at, 1, 10) FROM recognition_items
          WHERE reported_at IS NOT NULL
        ORDER BY local_date DESC
        """
    ).fetchall()
    return [row["local_date"] for row in rows]


def longest_streak(conn: sqlite3.Connection) -> int:
    """历史最长连续学习天数，不因中间断掉而清零。"""
    dates: list[date] = []
    for value in {
        row["local_date"]
        for row in conn.execute(
            """
            SELECT local_date FROM attempts
            UNION
            SELECT local_date FROM recognition_attempts
            UNION
            SELECT substr(reported_at, 1, 10) FROM recognition_items
              WHERE reported_at IS NOT NULL
            """
        )
    }:
        parsed = parse_iso_date(value)
        if parsed is not None:
            dates.append(parsed)
    dates.sort()
    best = 0
    current = 0
    previous: date | None = None
    for day in dates:
        if previous is not None and (day - previous).days == 1:
            current += 1
        else:
            current = 1
        best = max(best, current)
        previous = day
    return best
