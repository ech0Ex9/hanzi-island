"""课程结构：书 → 单元 → 课文 → 字位置。

- 数据来源：data/curriculum/1a.csv（一年级上册）、1b.csv（一年级下册）。
- 服务启动时幂等导入；CSV 改了重启即可更新。
- characters 表存「字的内容」，curriculum_items 存「字在教材里的位置」。
"""

from __future__ import annotations

import csv
import re
import sqlite3
from pathlib import Path
from typing import Any

from .db import DATA_DIR
from .serializers import char_to_dict

CURRICULUM_DIR = DATA_DIR / "curriculum"
AUDIO_DIR = Path(__file__).resolve().parent.parent / "web" / "assets" / "audio" / "pinyin"

# 书的固定信息（单元/课文/字位置来自 CSV）。
BOOK_META: dict[str, dict[str, Any]] = {
    "1a": {"title": "一年级上册", "edition": "2024 统编版", "sort_order": 1},
    "1b": {"title": "一年级下册", "edition": "2025 统编版", "sort_order": 2},
}

CSV_COLUMNS = [
    "book_id", "unit_no", "unit_title", "unit_kind", "lesson_no", "lesson_title",
    "lesson_kind", "lesson_order", "item_order", "char", "pinyin_override",
    "audio_key_override", "meaning_override", "words_override", "sentence_override",
    "mnemonic_override",
]

# 课程位置查询的公共 JOIN / ORDER BY：first_positions、list_lessons、多音字接口共用。
CURRICULUM_ITEM_JOIN = """
JOIN lessons l ON l.id = i.lesson_id
JOIN units u ON u.id = l.unit_id
JOIN books b ON b.id = u.book_id
"""
CURRICULUM_ITEM_ORDER = "ORDER BY b.sort_order, u.sort_order, l.sort_order, i.item_order"

OVERRIDE_COLUMNS = [
    "pinyin_override", "audio_key_override", "meaning_override",
    "words_override", "sentence_override", "mnemonic_override",
]

_RE_PREFIXED = re.compile(r"^(识字|汉语拼音|阅读)\s*(\d+)\s*(.*)$")
_RE_NUMBERED = re.compile(r"^(\d+)\s*(.*)$")


def split_lesson_title(title: str) -> tuple[str, str]:
    """「识字1 天地人」→ (1, 天地人)；「语文园地一」→ (园地一, 语文园地一)。"""
    text = title.strip()
    if text.startswith("语文园地"):
        return text.replace("语文", "", 1), text
    match = _RE_PREFIXED.match(text)
    if match:
        return match.group(2), (match.group(3).strip() or text)
    match = _RE_NUMBERED.match(text)
    if match:
        return match.group(1), (match.group(2).strip() or text)
    return "", text


def load_curriculum_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    return rows


def _parse_book_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """把 CSV 行整理成 units/lessons/items 树，顺序与文件一致。"""
    units: list[dict[str, Any]] = []
    unit_by_no: dict[int, dict[str, Any]] = {}
    for row in rows:
        unit_no = int(row["unit_no"])
        unit = unit_by_no.get(unit_no)
        if unit is None:
            unit = {
                "unit_no": unit_no,
                "title": row["unit_title"].strip(),
                "kind": row["unit_kind"].strip(),
                "lessons": [],
                "lesson_by_seq": {},
            }
            unit_by_no[unit_no] = unit
            units.append(unit)

        lesson_no_seq = int(row["lesson_order"])
        lesson = unit["lesson_by_seq"].get(lesson_no_seq)
        if lesson is None:
            display_no, display_title = split_lesson_title(row["lesson_title"])
            lesson = {
                "lesson_no": display_no or str(lesson_no_seq),
                "title": display_title,
                "kind": row["lesson_kind"].strip(),
                "sort_order": lesson_no_seq,
                "items": [],
            }
            unit["lesson_by_seq"][lesson_no_seq] = lesson
            unit["lessons"].append(lesson)

        lesson["items"].append(
            {
                "item_order": int(row["item_order"]),
                "char": row["char"].strip(),
                **{column: (row.get(column) or "").strip() or None for column in OVERRIDE_COLUMNS},
            }
        )
    return units


def import_curriculum(conn: sqlite3.Connection) -> dict[str, Any]:
    """把 data/curriculum/*.csv 导入 books/units/lessons/curriculum_items。幂等。"""
    if not CURRICULUM_DIR.exists():
        return {"books": []}

    summary: dict[str, Any] = {"books": []}
    for path in sorted(CURRICULUM_DIR.glob("*.csv")):
        book_id = path.stem
        meta = BOOK_META.get(book_id)
        if meta is None:
            raise ValueError(f"data/curriculum 里有未知册：{path.name}（BOOK_META 缺少 {book_id}）")

        rows = load_curriculum_csv(path)
        for index, row in enumerate(rows, start=2):
            missing = [column for column in CSV_COLUMNS if column not in (row or {})]
            if missing:
                raise ValueError(f"{path.name} 第 {index} 行缺少列：{', '.join(missing)}")
            if not (row.get("char") or "").strip():
                raise ValueError(f"{path.name} 第 {index} 行没有字")

        units = _parse_book_rows(rows)

        # 同册整体替换（先删子表，再删父表），保证 CSV 删除的行也会从库里消失。
        conn.execute(
            """
            DELETE FROM curriculum_items
            WHERE lesson_id IN (
              SELECT l.id FROM lessons l JOIN units u ON u.id = l.unit_id
              WHERE u.book_id = ?
            )
            """,
            (book_id,),
        )
        conn.execute(
            "DELETE FROM lessons WHERE unit_id IN (SELECT id FROM units WHERE book_id = ?)",
            (book_id,),
        )
        conn.execute("DELETE FROM units WHERE book_id = ?", (book_id,))
        conn.execute(
            """
            INSERT INTO books(id, title, edition, sort_order) VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              title = excluded.title, edition = excluded.edition,
              sort_order = excluded.sort_order
            """,
            (book_id, meta["title"], meta["edition"], meta["sort_order"]),
        )

        item_count = 0
        for unit in units:
            unit_id = f"{book_id}-u{unit['unit_no']}"
            conn.execute(
                "INSERT INTO units(id, book_id, unit_no, title, kind, sort_order) VALUES (?, ?, ?, ?, ?, ?)",
                (unit_id, book_id, unit["unit_no"], unit["title"], unit["kind"], unit["unit_no"]),
            )
            for lesson in unit["lessons"]:
                lesson_id = f"{unit_id}-l{lesson['sort_order']}"
                conn.execute(
                    "INSERT INTO lessons(id, unit_id, lesson_no, title, kind, sort_order) VALUES (?, ?, ?, ?, ?, ?)",
                    (lesson_id, unit_id, lesson["lesson_no"], lesson["title"], lesson["kind"], lesson["sort_order"]),
                )
                for item in lesson["items"]:
                    conn.execute(
                        """
                        INSERT INTO curriculum_items(
                          lesson_id, char, item_order, pinyin_override, audio_key_override,
                          meaning_override, words_override, sentence_override, mnemonic_override
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            lesson_id, item["char"], item["item_order"],
                            item["pinyin_override"], item["audio_key_override"],
                            item["meaning_override"], item["words_override"],
                            item["sentence_override"], item["mnemonic_override"],
                        ),
                    )
                    item_count += 1

        summary["books"].append(
            {"book_id": book_id, "units": len(units), "items": item_count}
        )
    return summary


def backfill_character_lesson_fields(conn: sqlite3.Connection) -> int:
    """用第一个课程位置回填 characters.lesson_id / lesson / lesson_order。

    旧字段保留只为兼容 NOT NULL 约束和旧查询，不再是数据源。
    """
    positions = first_positions(conn)
    updated = 0
    for row in conn.execute("SELECT char, lesson_id FROM characters").fetchall():
        position = positions.get(row["char"])
        if position is None:
            continue
        conn.execute(
            "UPDATE characters SET lesson_id = ?, lesson = ?, lesson_order = ? WHERE char = ?",
            (position["lesson_id"], position["lesson_title"], position["item_order"], row["char"]),
        )
        updated += 1
    return updated


def first_positions(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """每个字的第一个课程位置（书 → 单元 → 课文 → 字位置顺序）。"""
    rows = conn.execute(
        f"""
        SELECT i.char, i.item_order, i.pinyin_override, i.audio_key_override,
               l.id AS lesson_id, l.lesson_no, l.title AS lesson_title, l.kind AS lesson_kind,
               u.id AS unit_id, u.unit_no, u.title AS unit_title,
               b.id AS book_id, b.title AS book_title
        FROM curriculum_items i
        {CURRICULUM_ITEM_JOIN}
        {CURRICULUM_ITEM_ORDER}
        """
    ).fetchall()
    positions: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row["char"] in positions:
            continue
        positions[row["char"]] = {
            "book_id": row["book_id"],
            "book_title": row["book_title"],
            "unit_id": row["unit_id"],
            "unit_no": row["unit_no"],
            "unit_title": row["unit_title"],
            "lesson_id": row["lesson_id"],
            "lesson_no": row["lesson_no"],
            "lesson_title": row["lesson_title"],
            "lesson_kind": row["lesson_kind"],
            "item_order": row["item_order"],
            "reading_key": row["pinyin_override"],
        }
    return positions


def position_sort_key(position: dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        BOOK_META.get(position["book_id"], {}).get("sort_order", 99),
        position["unit_no"],
        _lesson_sort(position),
        position["item_order"],
    )


def _lesson_sort(position: dict[str, Any]) -> int:
    lesson_no = position.get("lesson_no") or ""
    if lesson_no.isdigit():
        return int(lesson_no)
    return 900  # 语文园地等没有数字编号的排在本单元数字课之后


def list_books(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """书目 → 单元 → 课文摘要（含进度）。"""
    books: list[dict[str, Any]] = []
    book_rows = conn.execute("SELECT * FROM books ORDER BY sort_order").fetchall()
    unit_rows = conn.execute("SELECT * FROM units ORDER BY book_id, sort_order").fetchall()
    lesson_rows = conn.execute(
        """
        SELECT l.id, l.unit_id, l.lesson_no, l.title, l.kind, l.sort_order,
               COUNT(i.id) AS positions,
               COUNT(c.char) AS content_chars,
               COUNT(CASE WHEN p.first_seen_at IS NOT NULL AND c.lesson_id = l.id THEN 1 END) AS learned
        FROM lessons l
        LEFT JOIN curriculum_items i ON i.lesson_id = l.id
        LEFT JOIN characters c ON c.char = i.char
        LEFT JOIN char_progress p ON p.char = i.char
        GROUP BY l.id
        ORDER BY l.sort_order
        """
    ).fetchall()

    lessons_by_unit: dict[str, list[dict[str, Any]]] = {}
    for row in lesson_rows:
        lessons_by_unit.setdefault(row["unit_id"], []).append(
            {
                "id": row["id"],
                "lesson_no": row["lesson_no"],
                "title": row["title"],
                "kind": row["kind"],
                "total": int(row["positions"]),
                "content_chars": int(row["content_chars"]),
                "learned": int(row["learned"]),
            }
        )

    units_by_book: dict[str, list[dict[str, Any]]] = {}
    for row in unit_rows:
        units_by_book.setdefault(row["book_id"], []).append(
            {
                "id": row["id"],
                "unit_no": row["unit_no"],
                "title": row["title"],
                "kind": row["kind"],
                "lessons": lessons_by_unit.get(row["id"], []),
            }
        )

    for row in book_rows:
        books.append(
            {
                "id": row["id"],
                "title": row["title"],
                "edition": row["edition"],
                "units": units_by_book.get(row["id"], []),
            }
        )
    return books


def get_book(conn: sqlite3.Connection, book_id: str) -> dict[str, Any] | None:
    books = list_books(conn)
    for book in books:
        if book["id"] == book_id:
            return book
    return None


def get_lesson(conn: sqlite3.Connection, lesson_id: str) -> dict[str, Any] | None:
    """某课的元信息 + 字（只返回有内容的字；总位置数另计）。"""
    lesson = conn.execute(
        """
        SELECT l.id, l.lesson_no, l.title, l.kind, l.sort_order,
               u.id AS unit_id, u.unit_no, u.title AS unit_title, u.kind AS unit_kind,
               b.id AS book_id, b.title AS book_title
        FROM lessons l
        JOIN units u ON u.id = l.unit_id
        JOIN books b ON b.id = u.book_id
        WHERE l.id = ?
        """,
        (lesson_id,),
    ).fetchone()
    if lesson is None:
        return None

    rows = conn.execute(
        """
        SELECT c.*, p.box, p.due_at, p.exposures, p.attempts, p.correct,
               p.wrong, p.streak, p.mastery, p.first_seen_at, p.last_seen_at,
               i.pinyin_override, i.audio_key_override, i.item_order
        FROM curriculum_items i
        JOIN characters c ON c.char = i.char
        JOIN char_progress p ON p.char = i.char
        WHERE i.lesson_id = ?
        ORDER BY i.item_order
        """,
        (lesson_id,),
    ).fetchall()

    total_positions = int(
        conn.execute(
            "SELECT COUNT(*) FROM curriculum_items WHERE lesson_id = ?", (lesson_id,)
        ).fetchone()[0]
    )
    chars = []
    for row in rows:
        data = char_to_dict(row)
        if row["pinyin_override"]:
            data["reading_key"] = row["pinyin_override"]
            data["pinyin"] = row["pinyin_override"]
        if row["audio_key_override"]:
            data["audio_key"] = row["audio_key_override"]
        chars.append(data)

    return {
        "id": lesson["id"],
        "lesson_no": lesson["lesson_no"],
        "title": lesson["title"],
        "kind": lesson["kind"],
        "book_id": lesson["book_id"],
        "book_title": lesson["book_title"],
        "unit_id": lesson["unit_id"],
        "unit_no": lesson["unit_no"],
        "unit_title": lesson["unit_title"],
        "total": total_positions,
        "learned": sum(1 for item in chars if item["progress"]["first_seen_at"]),
        "chars": chars,
    }


def list_lessons(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """按课程结构列出所有课（兼容旧返回形状，附单元/册信息）。

    没有内容的课也会出现（total = 位置数，chars 为空），首页可显示骨架。
    """
    items = conn.execute(
        f"""
        SELECT i.char AS pos_char, i.item_order, i.pinyin_override, i.audio_key_override,
               l.id AS lesson_id, l.lesson_no, l.title AS lesson_title, l.kind AS lesson_kind,
               u.id AS unit_id, u.unit_no, u.title AS unit_title,
               b.id AS book_id, b.title AS book_title,
               c.lesson_id AS char_lesson_id,
               c.*, p.box, p.due_at, p.exposures, p.attempts,
               p.correct, p.wrong, p.streak, p.mastery, p.first_seen_at, p.last_seen_at
        FROM curriculum_items i
        {CURRICULUM_ITEM_JOIN}
        LEFT JOIN characters c ON c.char = i.char
        LEFT JOIN char_progress p ON p.char = i.char
        {CURRICULUM_ITEM_ORDER}
        """
    ).fetchall()

    lessons: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for row in items:
        lesson_id = row["lesson_id"]
        lesson = by_id.get(lesson_id)
        if lesson is None:
            lesson = {
                "id": lesson_id,
                "lesson_no": row["lesson_no"],
                "title": row["lesson_title"],
                "kind": row["lesson_kind"],
                "book_id": row["book_id"],
                "book_title": row["book_title"],
                "unit_id": row["unit_id"],
                "unit_no": row["unit_no"],
                "unit_title": row["unit_title"],
                "total": 0,
                "learned": 0,
                "chars": [],
            }
            by_id[lesson_id] = lesson
            lessons.append(lesson)
        lesson["total"] += 1
        if row["pos_char"] is None or row["char"] is None:
            continue  # 内容还没写（P1/P2 补），先不算进卡片
        data = char_to_dict(row)
        if row["pinyin_override"]:
            data["reading_key"] = row["pinyin_override"]
            data["pinyin"] = row["pinyin_override"]
        if row["audio_key_override"]:
            data["audio_key"] = row["audio_key_override"]
        if data["progress"]["first_seen_at"] and row["char_lesson_id"] == lesson_id:
            lesson["learned"] += 1
        lesson["chars"].append(data)
    return lessons


def list_characters(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """全部有内容的字，按课程位置排序。"""
    from .srs import fetch_characters_with_progress

    rows = fetch_characters_with_progress(conn)
    positions = first_positions(conn)
    ordered = sorted(
        rows,
        key=lambda row: position_sort_key(positions[row["char"]])
        if row["char"] in positions
        else (99, 99, 999, row["lesson_order"] or 0),
    )
    result = []
    for row in ordered:
        data = char_to_dict(row)
        position = positions.get(row["char"])
        if position:
            data["book_id"] = position["book_id"]
            data["unit_id"] = position["unit_id"]
            data["lesson_id"] = position["lesson_id"]
        result.append(data)
    return result
