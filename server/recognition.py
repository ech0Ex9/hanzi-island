"""艾宾浩斯认字强化：整体过一遍 + 每日复习。

设计见 docs/specs/2026-11-13-ebbinghaus-recognition.md。

和现有 Leitner 排队（char_progress）相互独立：
- 自评「认识」只进入 R1，次日答题验证；
- 自评「不认识」进入 R0，当天/次日先看字卡再答题；
- 只有答题结果才能升级，避免「自评会」直接算掌握。
"""

from __future__ import annotations

import sqlite3
import unicodedata
import uuid
from datetime import date, timedelta
from typing import Any

from . import curriculum
from .db import now_iso, today_str
from .serializers import char_to_dict

# R0..R7 对应的下次复习间隔（天）。
RECOGNITION_INTERVAL_DAYS = {0: 0, 1: 1, 2: 2, 3: 4, 4: 7, 5: 15, 6: 30, 7: 60}
MAX_REVIEWS_PER_SESSION = 15
SCOPE_TITLES = {
    "literacy": "幼儿识字 1300",
    "all": "全部课内",
    "1a": "一年级上册",
    "1b": "一年级下册",
}


def scope_title(scope: str) -> str:
    if scope in SCOPE_TITLES:
        return SCOPE_TITLES[scope]
    if scope.startswith("unit:"):
        return "单元"
    return scope


def due_date_for_stage(stage: int, base: date | None = None) -> str:
    days = RECOGNITION_INTERVAL_DAYS[max(0, min(7, int(stage)))]
    return ((base or date.today()) + timedelta(days=days)).isoformat()


def stage_after_attempt(
    self_report: str,
    stage: int,
    streak: int,
    attempts: int,
    is_correct: bool,
) -> tuple[int, int]:
    """答题后的新阶段和连续答对次数。

    - 答对升一级；自评「不认识」的第一次答对跳一级。
    - 连续答对不足 2 次时，不允许进入 R4 以上。
    - 答错降一级，最低 R0。
    """
    stage = max(0, min(7, int(stage)))
    streak = max(0, int(streak))
    attempts = max(0, int(attempts))
    if is_correct:
        streak += 1
        step = 2 if (self_report == "unknown" and attempts == 0) else 1
        target = min(7, stage + step)
        if target >= 4 and streak < 2:
            target = 3
        return max(stage, target), streak
    return max(0, stage - 1), 0


def _scope_members(conn: sqlite3.Connection, scope: str) -> set[str] | None:
    """范围里的不同字。按「在册/单元里出现过」算，不只看第一次出现的位置。

    这样 1a 279 + 1b 413 会包含 4 个跨册重复字；全部 688 仍按字去重。
    """
    if scope == "all":
        rows = conn.execute(
            "SELECT DISTINCT char FROM curriculum_items"
        ).fetchall()
        return {row["char"] for row in rows}
    if scope == "literacy":
        rows = conn.execute("SELECT char FROM literacy_entries").fetchall()
        return {row["char"] for row in rows}
    if scope.startswith("unit:"):
        unit_id = scope.split(":", 1)[1]
        rows = conn.execute(
            """
            SELECT DISTINCT i.char
            FROM curriculum_items i
            JOIN lessons l ON l.id = i.lesson_id
            WHERE l.unit_id = ?
            """,
            (unit_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT DISTINCT i.char
            FROM curriculum_items i
            JOIN lessons l ON l.id = i.lesson_id
            JOIN units u ON u.id = l.unit_id
            WHERE u.book_id = ?
            """,
            (scope,),
        ).fetchall()
    return {row["char"] for row in rows}


def _scope_chars(conn: sqlite3.Connection, scope: str) -> list[dict[str, Any]]:
    if scope == "literacy":
        rows = conn.execute(
            """
            SELECT c.*, p.box, p.due_at, p.exposures, p.attempts, p.correct,
                   p.wrong, p.streak, p.mastery, p.first_seen_at, p.last_seen_at
            FROM literacy_entries l
            JOIN characters c ON c.char = l.char
            JOIN char_progress p ON p.char = c.char
            ORDER BY l.sort_order
            """
        ).fetchall()
        return [char_to_dict(row) for row in rows]
    chars = curriculum.list_characters(conn)
    members = _scope_members(conn, scope)
    if members is None:
        return chars
    return [item for item in chars if item["char"] in members]


def _delete_scope_items(conn: sqlite3.Connection, scope: str) -> None:
    """重新过一遍时，先清掉这个范围的自评和复习安排。

    认字答题历史（recognition_attempts）保留，方便家长回看；只重置当前状态。
    """
    if scope == "all":
        conn.execute(
            "DELETE FROM recognition_items WHERE char IN (SELECT char FROM curriculum_items)"
        )
        return
    if scope == "literacy":
        conn.execute(
            "DELETE FROM recognition_items WHERE char IN (SELECT char FROM literacy_entries)"
        )
        return
    if scope.startswith("unit:"):
        unit_id = scope.split(":", 1)[1]
        conn.execute(
            """
            DELETE FROM recognition_items
            WHERE char IN (
              SELECT DISTINCT i.char
              FROM curriculum_items i
              JOIN lessons l ON l.id = i.lesson_id
              WHERE l.unit_id = ?
            )
            """,
            (unit_id,),
        )
        return
    conn.execute(
        """
        DELETE FROM recognition_items
        WHERE char IN (
          SELECT DISTINCT i.char
          FROM curriculum_items i
          JOIN lessons l ON l.id = i.lesson_id
          JOIN units u ON u.id = l.unit_id
          WHERE u.book_id = ?
        )
        """,
        (scope,),
    )


def _scope_options(conn: sqlite3.Connection, total: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT b.id, b.title, COUNT(DISTINCT i.char) AS total
        FROM books b
        JOIN units u ON u.book_id = b.id
        JOIN lessons l ON l.unit_id = u.id
        JOIN curriculum_items i ON i.lesson_id = l.id
        GROUP BY b.id, b.title, b.sort_order
        ORDER BY b.sort_order
        """
    ).fetchall()
    literacy_total = int(
        conn.execute("SELECT COUNT(*) FROM literacy_entries").fetchone()[0]
    )
    options = []
    if literacy_total:
        options.append(
            {"id": "literacy", "title": SCOPE_TITLES["literacy"], "total": literacy_total}
        )
    options.append({"id": "all", "title": SCOPE_TITLES["all"], "total": total})
    options.extend(
        {"id": row["id"], "title": row["title"], "total": int(row["total"])}
        for row in rows
    )
    return options


def _run_dict(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    total = int(row["total"] or 0)
    known = int(row["known"] or 0)
    unknown = int(row["unknown"] or 0)
    reported = known + unknown
    return {
        "id": row["id"],
        "scope": row["scope"],
        "scope_title": scope_title(row["scope"]),
        "started_at": row["started_at"],
        "ended_at": row["ended_at"],
        "total": total,
        "reported": reported,
        "known": known,
        "unknown": unknown,
        "status": row["status"],
        "percent": round(reported / total * 100) if total else 0,
    }


def _next_for_run(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any] | None:
    if row["status"] != "active":
        return None
    chars = _scope_chars(conn, row["scope"])
    reported = {
        item["char"]
        for item in conn.execute(
            "SELECT char FROM recognition_items WHERE run_id = ?", (row["id"],)
        )
    }
    for index, item in enumerate(chars, start=1):
        if item["char"] not in reported:
            return {
                "char": item["char"],
                "index": index,
                "total": len(chars),
            }
    return None


def _active_run(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM recognition_runs WHERE status = 'active' "
        "ORDER BY started_at DESC LIMIT 1"
    ).fetchone()


def _latest_run(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM recognition_runs ORDER BY started_at DESC LIMIT 1"
    ).fetchone()


def summary(conn: sqlite3.Connection) -> dict[str, Any]:
    literacy_total = int(
        conn.execute("SELECT COUNT(*) FROM literacy_entries").fetchone()[0]
    )
    has_literacy = literacy_total > 0
    total = (
        literacy_total
        if has_literacy
        else int(conn.execute("SELECT COUNT(*) FROM characters").fetchone()[0])
    )
    scope_filter = (
        "WHERE char IN (SELECT char FROM literacy_entries)" if has_literacy else ""
    )
    literacy_item_filter = (
        "AND i.char IN (SELECT char FROM literacy_entries)" if has_literacy else ""
    )
    today = today_str()
    row = conn.execute(
        f"""
        SELECT
          COUNT(*) AS reported,
          COALESCE(SUM(CASE WHEN self_report = 'known' THEN 1 ELSE 0 END), 0) AS known,
          COALESCE(SUM(CASE WHEN self_report = 'unknown' THEN 1 ELSE 0 END), 0) AS unknown,
          COALESCE(SUM(CASE WHEN first_quiz_at IS NOT NULL THEN 1 ELSE 0 END), 0) AS verified,
          COALESCE(SUM(CASE WHEN self_report = 'known' AND first_quiz_correct = 0 THEN 1 ELSE 0 END), 0) AS overconfident,
          COALESCE(SUM(CASE WHEN self_report = 'unknown' AND first_quiz_correct = 1 THEN 1 ELSE 0 END), 0) AS underestimated,
          COALESCE(SUM(CASE WHEN stage >= 7 THEN 1 ELSE 0 END), 0) AS mastered,
          COALESCE(SUM(CASE WHEN stage BETWEEN 4 AND 6 THEN 1 ELSE 0 END), 0) AS familiar
        FROM recognition_items
        {scope_filter}
        """
    ).fetchone()

    due = int(
        conn.execute(
            """
            SELECT COUNT(*) FROM recognition_items i
            WHERE i.due_at <= ?
              AND NOT EXISTS (
                SELECT 1 FROM recognition_attempts a
                WHERE a.char = i.char AND a.local_date = ?
                  AND a.ts >= i.reported_at
              )
            """,
            (today, today),
        ).fetchone()[0]
    )
    next_due_row = conn.execute(
        "SELECT MIN(due_at) AS next_due FROM recognition_items WHERE due_at > ?",
        (today,),
    ).fetchone()
    next_due = next_due_row["next_due"] if next_due_row else None

    stage_counts = {str(stage): 0 for stage in range(8)}
    for stage_row in conn.execute(
        f"SELECT stage, COUNT(*) AS n FROM recognition_items {scope_filter} GROUP BY stage"
    ):
        stage_counts[str(int(stage_row["stage"]))] = int(stage_row["n"])

    today_row = conn.execute(
        """
        SELECT COUNT(*) AS n, COALESCE(SUM(result), 0) AS c
        FROM recognition_attempts WHERE local_date = ?
        """,
        (today,),
    ).fetchone()
    today_attempts = int(today_row["n"])
    today_correct = int(today_row["c"])

    overconfident_items = [
        {
            "char": item["char"],
            "pinyin": item["pinyin"],
            "meaning": item["meaning"],
        }
        for item in conn.execute(
            f"""
            SELECT c.char, c.pinyin, c.meaning
            FROM recognition_items i
            JOIN characters c ON c.char = i.char
            WHERE i.self_report = 'known' AND i.first_quiz_correct = 0
              {literacy_item_filter}
            ORDER BY i.last_seen_at DESC
            LIMIT 8
            """
        )
    ]
    underestimated_items = [
        {
            "char": item["char"],
            "pinyin": item["pinyin"],
            "meaning": item["meaning"],
        }
        for item in conn.execute(
            f"""
            SELECT c.char, c.pinyin, c.meaning
            FROM recognition_items i
            JOIN characters c ON c.char = i.char
            WHERE i.self_report = 'unknown' AND i.first_quiz_correct = 1
              {literacy_item_filter}
            ORDER BY i.last_seen_at DESC
            LIMIT 8
            """
        )
    ]

    active = _active_run(conn)
    latest = _latest_run(conn)
    active_data = _run_dict(conn, active) if active else None
    if active_data:
        active_data["next"] = _next_for_run(conn, active)
    latest_data = _run_dict(conn, latest) if latest else None

    textbook_total = int(
        conn.execute("SELECT COUNT(DISTINCT char) FROM curriculum_items").fetchone()[0]
    )
    reported = int(row["reported"] or 0)
    return {
        "total": total,
        "reported": reported,
        "unreported": max(0, total - reported),
        "self_known": int(row["known"] or 0),
        "self_unknown": int(row["unknown"] or 0),
        "verified": int(row["verified"] or 0),
        "overconfident": int(row["overconfident"] or 0),
        "underestimated": int(row["underestimated"] or 0),
        "mastered": int(row["mastered"] or 0),
        "familiar": int(row["familiar"] or 0),
        "due": due,
        "next_due": next_due,
        "today_attempts": today_attempts,
        "today_correct": today_correct,
        "today_accuracy": round(today_correct / today_attempts * 100) if today_attempts else 0,
        "by_stage": stage_counts,
        "active_run": active_data,
        "latest_run": latest_data,
        "scopes": _scope_options(conn, textbook_total),
        "overconfident_items": overconfident_items,
        "underestimated_items": underestimated_items,
        "review_limit": MAX_REVIEWS_PER_SESSION,
    }


def start_run(
    conn: sqlite3.Connection, scope: str, restart: bool = False
) -> dict[str, Any]:
    chars = _scope_chars(conn, scope)
    if not chars:
        raise ValueError("这个范围没有字")

    if not restart:
        active = _active_run(conn)
        if active:
            data = _run_dict(conn, active)
            data["next"] = _next_for_run(conn, active)
            return {"run": data, "next": data["next"], "summary": summary(conn)}

    if restart:
        conn.execute(
            "UPDATE recognition_runs SET status = 'finished', ended_at = COALESCE(ended_at, ?) "
            "WHERE status = 'active'",
            (now_iso(),),
        )
        _delete_scope_items(conn, scope)

    run_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO recognition_runs(id, started_at, scope, total, status) "
        "VALUES (?, ?, ?, ?, 'active')",
        (run_id, now_iso(), scope, len(chars)),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM recognition_runs WHERE id = ?", (run_id,)).fetchone()
    data = _run_dict(conn, row)
    data["next"] = _next_for_run(conn, row)
    return {"run": data, "next": data["next"], "summary": summary(conn)}


def report(
    conn: sqlite3.Connection, run_id: str, char: str, report_value: str
) -> dict[str, Any]:
    if report_value not in {"known", "unknown"}:
        raise ValueError("report 只能是 known 或 unknown")
    run = conn.execute("SELECT * FROM recognition_runs WHERE id = ?", (run_id,)).fetchone()
    if run is None:
        raise KeyError("没有这一轮认字")
    if run["status"] != "active":
        raise ValueError("这一轮已经过完了")

    chars = {item["char"] for item in _scope_chars(conn, run["scope"])}
    if char not in chars:
        raise ValueError("这个字不在本轮范围里")

    existing = conn.execute(
        "SELECT self_report, attempts FROM recognition_items WHERE char = ? AND run_id = ?",
        (char, run_id),
    ).fetchone()
    ts = now_iso()

    # 回看时点到原来的标记：不重写排程，直接返回当前进度。
    if existing is not None and existing["self_report"] == report_value:
        data = _run_dict(conn, run)
        data["next"] = _next_for_run(conn, run)
        return {"run": data, "next": data["next"], "summary": summary(conn)}

    if existing is not None and int(existing["attempts"]) > 0:
        # 这个字已经进入每日复习：回看改标只改标签，保留答题历史和下次复习时间。
        conn.execute(
            "UPDATE recognition_items SET self_report = ?, updated_at = ? WHERE char = ?",
            (report_value, ts, char),
        )
    else:
        stage = 1 if report_value == "known" else 0
        due_at = due_date_for_stage(stage)
        conn.execute(
            """
            INSERT INTO recognition_items(
              char, run_id, self_report, reported_at, stage, due_at,
              attempts, correct, wrong, streak, first_quiz_at, first_quiz_correct,
              last_result, last_seen_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, 0, NULL, NULL, NULL, NULL, ?)
            ON CONFLICT(char) DO UPDATE SET
              run_id = excluded.run_id,
              self_report = excluded.self_report,
              reported_at = excluded.reported_at,
              stage = excluded.stage,
              due_at = excluded.due_at,
              attempts = 0,
              correct = 0,
              wrong = 0,
              streak = 0,
              first_quiz_at = NULL,
              first_quiz_correct = NULL,
              last_result = NULL,
              last_seen_at = NULL,
              updated_at = excluded.updated_at
            """,
            (char, run_id, report_value, ts, stage, due_at, ts),
        )

    known_delta = 0
    unknown_delta = 0
    if existing is None:
        if report_value == "known":
            known_delta = 1
        else:
            unknown_delta = 1
    elif existing["self_report"] != report_value:
        if report_value == "known":
            known_delta, unknown_delta = 1, -1
        else:
            known_delta, unknown_delta = -1, 1

    conn.execute(
        "UPDATE recognition_runs SET known = MAX(0, known + ?), "
        "unknown = MAX(0, unknown + ?) WHERE id = ?",
        (known_delta, unknown_delta, run_id),
    )
    updated = conn.execute("SELECT * FROM recognition_runs WHERE id = ?", (run_id,)).fetchone()
    if int(updated["known"]) + int(updated["unknown"]) >= int(updated["total"]):
        conn.execute(
            "UPDATE recognition_runs SET status = 'finished', ended_at = ? WHERE id = ?",
            (ts, run_id),
        )
        updated = conn.execute(
            "SELECT * FROM recognition_runs WHERE id = ?", (run_id,)
        ).fetchone()
    conn.commit()

    data = _run_dict(conn, updated)
    data["next"] = _next_for_run(conn, updated)
    return {"run": data, "next": data["next"], "summary": summary(conn)}


RECOGNITION_ITEM_COLUMNS = """
    i.char, i.run_id, i.self_report, i.stage, i.due_at, i.attempts,
    i.correct, i.wrong, i.first_quiz_at, i.first_quiz_correct, i.updated_at,
    c.pinyin, c.meaning, c.lesson, c.words_json
"""


def _plain_pinyin(value: str | None) -> str:
    """去掉声调，方便用 kuai 搜到 kuài。"""
    text = unicodedata.normalize("NFD", value or "")
    return "".join(char for char in text if not unicodedata.combining(char)).lower()


def _item_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "char": row["char"],
        "run_id": row["run_id"],
        "self_report": row["self_report"],
        "stage": int(row["stage"]),
        "due_at": row["due_at"],
        "attempts": int(row["attempts"]),
        "correct": int(row["correct"]),
        "wrong": int(row["wrong"]),
        "first_quiz_at": row["first_quiz_at"],
        "first_quiz_correct": row["first_quiz_correct"],
        "updated_at": row["updated_at"],
        "pinyin": row["pinyin"],
        "meaning": row["meaning"],
        "lesson": row["lesson"],
    }


def list_items(
    conn: sqlite3.Connection, query: str = "", limit: int = 60
) -> dict[str, Any]:
    """已经自评过的字，供「改自评」页面搜索。"""
    query = (query or "").strip()
    limit = max(1, min(200, int(limit)))
    base_sql = f"""
        SELECT {RECOGNITION_ITEM_COLUMNS}
        FROM recognition_items i
        JOIN characters c ON c.char = i.char
        ORDER BY CASE i.self_report WHEN 'unknown' THEN 0 ELSE 1 END,
                 i.updated_at DESC, i.char
    """
    if not query:
        rows = conn.execute(f"{base_sql} LIMIT ?", (limit,)).fetchall()
        total = int(
            conn.execute("SELECT COUNT(*) FROM recognition_items").fetchone()[0]
        )
    else:
        # 认字表最多 1300 条，直接取出后在 Python 里做去声调拼音匹配，
        # 这样输入 kuai 也能搜到 kuài。
        rows = conn.execute(base_sql).fetchall()
        needle = _plain_pinyin(query)
        matched = [
            row
            for row in rows
            if query in (row["char"] or "")
            or needle in _plain_pinyin(row["pinyin"])
            or needle in (row["meaning"] or "").lower()
            or needle in (row["lesson"] or "").lower()
            or needle in (row["words_json"] or "").lower()
        ]
        total = len(matched)
        rows = matched[:limit]
    return {
        "items": [_item_dict(row) for row in rows],
        "total": total,
        "query": query,
        "limit": limit,
    }


def set_report(
    conn: sqlite3.Connection, char: str, report_value: str
) -> dict[str, Any]:
    """修改一个已经自评过的字。

    还没复习过的字（attempts=0）会按新自评重排阶段和下次复习时间；
    已经复习过的字只改自评标签，保留原来的学习历史和复习时间。
    """
    if report_value not in {"known", "unknown"}:
        raise ValueError("report 只能是 known 或 unknown")

    row = conn.execute(
        f"SELECT {RECOGNITION_ITEM_COLUMNS} FROM recognition_items i "
        "JOIN characters c ON c.char = i.char WHERE i.char = ?",
        (char,),
    ).fetchone()
    if row is None:
        raise KeyError("这个字还没有自评记录")

    run_id = row["run_id"]
    attempts = int(row["attempts"])
    changed = row["self_report"] != report_value
    schedule_changed = bool(changed and attempts == 0)
    ts = now_iso()

    if changed:
        if schedule_changed:
            stage = 1 if report_value == "known" else 0
            due_at = due_date_for_stage(stage)
            conn.execute(
                """
                UPDATE recognition_items SET
                  self_report = ?, reported_at = ?, stage = ?, due_at = ?,
                  attempts = 0, correct = 0, wrong = 0, streak = 0,
                  first_quiz_at = NULL, first_quiz_correct = NULL,
                  last_result = NULL, last_seen_at = NULL, updated_at = ?
                WHERE char = ?
                """,
                (report_value, ts, stage, due_at, ts, char),
            )
        else:
            conn.execute(
                "UPDATE recognition_items SET self_report = ?, updated_at = ? "
                "WHERE char = ?",
                (report_value, ts, char),
            )

        if run_id:
            # 以 items 为准重算，避免多次修改后计数漂移。
            conn.execute(
                """
                UPDATE recognition_runs SET
                  known = (SELECT COUNT(*) FROM recognition_items
                           WHERE run_id = ? AND self_report = 'known'),
                  unknown = (SELECT COUNT(*) FROM recognition_items
                             WHERE run_id = ? AND self_report = 'unknown')
                WHERE id = ?
                """,
                (run_id, run_id, run_id),
            )
            run = conn.execute(
                "SELECT * FROM recognition_runs WHERE id = ?", (run_id,)
            ).fetchone()
            if (
                run
                and run["status"] == "active"
                and int(run["known"]) + int(run["unknown"]) >= int(run["total"])
            ):
                conn.execute(
                    "UPDATE recognition_runs SET status = 'finished', ended_at = ? "
                    "WHERE id = ?",
                    (ts, run_id),
                )
        conn.commit()

    updated = conn.execute(
        f"SELECT {RECOGNITION_ITEM_COLUMNS} FROM recognition_items i "
        "JOIN characters c ON c.char = i.char WHERE i.char = ?",
        (char,),
    ).fetchone()
    return {
        "item": _item_dict(updated),
        "changed": changed,
        "schedule_changed": schedule_changed,
        "summary": summary(conn),
    }


def today(conn: sqlite3.Connection) -> dict[str, Any]:
    data = summary(conn)
    today_value = today_str()
    rows = conn.execute(
        """
        SELECT
          i.char AS rec_char,
          i.self_report AS rec_self_report,
          i.stage AS rec_stage,
          i.due_at AS rec_due_at,
          i.attempts AS rec_attempts,
          i.correct AS rec_correct,
          i.wrong AS rec_wrong,
          i.streak AS rec_streak,
          i.first_quiz_at AS rec_first_quiz_at,
          i.first_quiz_correct AS rec_first_quiz_correct,
          i.last_result AS rec_last_result,
          c.*, p.box, p.due_at, p.exposures, p.attempts, p.correct,
          p.wrong, p.streak, p.mastery, p.first_seen_at, p.last_seen_at
        FROM recognition_items i
        JOIN characters c ON c.char = i.char
        JOIN char_progress p ON p.char = i.char
        WHERE i.due_at <= ?
          AND NOT EXISTS (
            SELECT 1 FROM recognition_attempts a
            WHERE a.char = i.char AND a.local_date = ?
              AND a.ts >= i.reported_at
          )
        ORDER BY CASE i.self_report WHEN 'unknown' THEN 0 ELSE 1 END,
                 i.due_at ASC, i.stage ASC, i.updated_at ASC
        LIMIT ?
        """,
        (today_value, today_value, MAX_REVIEWS_PER_SESSION),
    ).fetchall()

    positions = curriculum.first_positions(conn)
    items: list[dict[str, Any]] = []
    for row in rows:
        item = char_to_dict(row)
        item["mode"] = "recognition"
        item["recognition_mode"] = (
            "learn"
            if row["rec_self_report"] == "unknown" and int(row["rec_attempts"]) == 0
            else "quiz"
        )
        item["stage"] = "learn" if item["recognition_mode"] == "learn" else "quiz"
        item["self_report"] = row["rec_self_report"]
        item["recognition_stage"] = int(row["rec_stage"])
        item["recognition_due_at"] = row["rec_due_at"]
        item["recognition_attempts"] = int(row["rec_attempts"])
        item["first_quiz_correct"] = row["rec_first_quiz_correct"]
        position = positions.get(item["char"])
        if position:
            item.update(
                {
                    "book_id": position["book_id"],
                    "book_title": position["book_title"],
                    "unit_id": position["unit_id"],
                    "unit_title": position["unit_title"],
                    "lesson_id": position["lesson_id"],
                    "lesson_title": position["lesson_title"],
                    "reading_key": position["reading_key"],
                }
            )
        items.append(item)

    return {
        "items": items,
        "due": int(data["due"]),
        "backlog": max(0, int(data["due"]) - len(items)),
        "limit": MAX_REVIEWS_PER_SESSION,
        "summary": data,
    }


def attempt(
    conn: sqlite3.Connection,
    char: str,
    is_correct: bool,
    response_ms: int | None = None,
) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM recognition_items WHERE char = ?", (char,)
    ).fetchone()
    if row is None:
        raise KeyError("这个字还没有自评记录")

    stage_before = int(row["stage"])
    attempts = int(row["attempts"])
    first_quiz = attempts == 0
    stage_after, streak = stage_after_attempt(
        row["self_report"], stage_before, int(row["streak"]), attempts, is_correct
    )
    due_at = due_date_for_stage(stage_after)
    ts = now_iso()

    overconfident = bool(first_quiz and not is_correct and row["self_report"] == "known")
    underestimated = bool(first_quiz and is_correct and row["self_report"] == "unknown")

    conn.execute(
        """
        UPDATE recognition_items SET
          stage = ?, due_at = ?, attempts = attempts + 1,
          correct = correct + ?, wrong = wrong + ?, streak = ?,
          first_quiz_at = COALESCE(first_quiz_at, ?),
          first_quiz_correct = COALESCE(first_quiz_correct, ?),
          last_result = ?, last_seen_at = ?, updated_at = ?
        WHERE char = ?
        """,
        (
            stage_after,
            due_at,
            int(is_correct),
            int(not is_correct),
            streak,
            ts if first_quiz else None,
            int(is_correct) if first_quiz else None,
            int(is_correct),
            ts,
            ts,
            char,
        ),
    )
    conn.execute(
        """
        INSERT INTO recognition_attempts(
          char, ts, local_date, result, stage_before, stage_after, response_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (char, ts, today_str(), int(is_correct), stage_before, stage_after, response_ms),
    )
    conn.commit()

    return {
        "char": char,
        "stage_before": stage_before,
        "stage": stage_after,
        "streak": streak,
        "due_at": due_at,
        "due_in_days": RECOGNITION_INTERVAL_DAYS[stage_after],
        "overconfident": overconfident,
        "underestimated": underestimated,
    }


def print_sheet(conn: sqlite3.Connection) -> dict[str, Any]:
    """打印清单：自评不认识的字 + 自评认识但答错过的高估字。"""
    records = {
        row["char"]: row
        for row in conn.execute(
            "SELECT char, self_report, first_quiz_correct, stage, due_at "
            "FROM recognition_items"
        )
    }
    items: list[dict[str, Any]] = []
    unknown = 0
    overconfident = 0
    for item in curriculum.list_characters(conn):
        record = records.get(item["char"])
        if record is None:
            continue
        if record["self_report"] == "unknown":
            reason = "unknown"
            unknown += 1
        elif record["first_quiz_correct"] == 0:
            reason = "overconfident"
            overconfident += 1
        else:
            continue
        items.append(
            {
                "char": item["char"],
                "pinyin": item["pinyin"],
                "words": (item.get("words") or [])[:2],
                "reason": reason,
            }
        )
    return {
        "items": items,
        "total": len(items),
        "unknown": unknown,
        "overconfident": overconfident,
    }


def get_run(conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM recognition_runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        return None
    data = _run_dict(conn, row)
    data["next"] = _next_for_run(conn, row)
    return {"run": data, "next": data["next"], "summary": summary(conn)}


def item_at(conn: sqlite3.Connection, run_id: str, index: int) -> dict[str, Any]:
    """按本轮顺序取第 index 个字，供孩子回看和改自评。

    index 从 1 开始，顺序和整体过字时完全一致；未标过的字也会返回，
    但 reported=False，客户端据此判断是否还能继续往前回看。
    """
    row = conn.execute("SELECT * FROM recognition_runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise KeyError("没有这一轮认字")
    chars = _scope_chars(conn, row["scope"])
    total = len(chars)
    if index < 1 or index > total:
        raise ValueError(f"序号必须在 1 到 {total} 之间")
    char = chars[index - 1]["char"]
    item = conn.execute(
        "SELECT self_report FROM recognition_items WHERE char = ? AND run_id = ?",
        (char, run_id),
    ).fetchone()
    return {
        "run": _run_dict(conn, row),
        "item": {
            "char": char,
            "index": index,
            "total": total,
            "reported": item is not None,
            "self_report": item["self_report"] if item else None,
        },
        "summary": summary(conn),
    }
