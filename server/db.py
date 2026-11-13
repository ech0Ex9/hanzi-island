#!/usr/bin/env python3
"""SQLite 连接、初始化、种子数据与通用工具。

数据库拆成两个：
- data/content.db：字、课程结构（characters / books / units / lessons / curriculum_items）
- data/stats.db：学习记录、进度、设置（sessions / attempts / char_progress / settings / events）

统计库连接时会 ATTACH 内容库，并建 TEMP VIEW 映射内容表，这样原有查询可以继续
直接写 `characters`、`curriculum_items`（只读）。写内容表必须用 connect_content()。
"""

from __future__ import annotations

import csv
import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CONTENT_DB_PATH = DATA_DIR / "content.db"
STATS_DB_PATH = DATA_DIR / "stats.db"
# 拆分前的单库；只在首次创建 stats.db 时迁移统计表，之后原样保留作备份。
LEGACY_DB_PATH = DATA_DIR / "hanzi.legacy.db"
CSV_PATH = DATA_DIR / "characters.csv"
LITERACY_CSV_PATH = DATA_DIR / "literacy_1300.csv"
CONTENT_SCHEMA_PATH = Path(__file__).resolve().parent / "content_schema.sql"
STATS_SCHEMA_PATH = Path(__file__).resolve().parent / "stats_schema.sql"

SCHEMA_VERSION = 4

CONTENT_TABLES = (
    "characters",
    "books",
    "units",
    "lessons",
    "curriculum_items",
    "literacy_entries",
)

DEFAULT_SETTINGS = {
    "new_per_day": 5,
    "sound": True,
    "auto_play_audio": True,
    "reduce_motion": False,
    "theme": "paper",
    "pinyin_mode": "auto",
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def today_str() -> str:
    return date.today().isoformat()


def _connect(path: Path) -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def connect_content() -> sqlite3.Connection:
    return _connect(CONTENT_DB_PATH)


def connect_stats() -> sqlite3.Connection:
    conn = _connect(STATS_DB_PATH)
    conn.execute("ATTACH DATABASE ? AS content", (str(CONTENT_DB_PATH),))
    for table in CONTENT_TABLES:
        conn.execute(
            f"CREATE TEMP VIEW IF NOT EXISTS {table} AS SELECT * FROM content.{table}"
        )
    return conn


def connect() -> sqlite3.Connection:
    """统计库连接（内容表以只读 TEMP VIEW 形式可用）。"""
    return connect_stats()


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    conn = connect_stats()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_content_db() -> Iterator[sqlite3.Connection]:
    conn = connect_content()
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    _init_content()
    _init_stats()


def _init_content() -> None:
    conn = connect_content()
    try:
        conn.executescript(CONTENT_SCHEMA_PATH.read_text(encoding="utf-8"))
        _seed_characters(conn)
        _seed_literacy(conn)
        from . import curriculum

        curriculum.import_curriculum(conn)
        curriculum.backfill_character_lesson_fields(conn)
        conn.commit()
    finally:
        conn.close()


def _init_stats() -> None:
    first_time = not STATS_DB_PATH.exists()
    with get_db() as conn:
        conn.executescript(STATS_SCHEMA_PATH.read_text(encoding="utf-8"))
        _apply_migrations(conn)
        if first_time:
            _migrate_legacy_stats(conn)
        _ensure_settings(conn)
        _seed_progress(conn)
        conn.commit()


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """轻量迁移：旧统计库的 attempts 表补 reading_key 列。"""
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(attempts)").fetchall()
    }
    if columns and "reading_key" not in columns:
        conn.execute("ALTER TABLE attempts ADD COLUMN reading_key TEXT")
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
        (SCHEMA_VERSION, now_iso()),
    )


def _migrate_legacy_stats(conn: sqlite3.Connection) -> None:
    """首次拆分时，把旧 data/hanzi.db 的统计表复制到 stats.db（保留进度）。"""
    if not LEGACY_DB_PATH.exists():
        return
    conn.execute("ATTACH DATABASE ? AS legacy", (str(LEGACY_DB_PATH),))
    try:
        # sessions 先复制，attempts / events 的外键才能通过。
        for table in ("sessions", "char_progress", "attempts", "settings", "events"):
            exists = conn.execute(
                "SELECT 1 FROM legacy.sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone()
            if not exists:
                continue
            conn.execute(f"INSERT OR IGNORE INTO {table} SELECT * FROM legacy.{table}")
        # DETACH 不能在未提交的事务里执行。
        conn.commit()
    finally:
        try:
            conn.execute("DETACH DATABASE legacy")
        except sqlite3.OperationalError:
            pass


def _seed_characters(conn: sqlite3.Connection) -> None:
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"找不到字表：{CSV_PATH}")

    with CSV_PATH.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    seen: set[str] = set()
    for row in rows:
        char = (row.get("char") or "").strip()
        if not char:
            continue
        if char in seen:
            raise ValueError(f"字表里有重复字：{char}")
        seen.add(char)

        words = [w.strip() for w in (row.get("words") or "").split("|") if w.strip()]
        confusions = [c.strip() for c in (row.get("confusions") or "").split("|") if c.strip()]
        quiz_types = [q.strip() for q in (row.get("quiz_types") or "").split("|") if q.strip()]

        # characters.csv 从 P0 起只存「字的内容」；课程位置（lesson_id/lesson/lesson_order）
        # 由 curriculum_items 导入后回填（见 _init_content），旧字段仅为兼容保留。
        conn.execute(
            """
            INSERT INTO characters (
              char, pinyin, lesson_id, lesson, lesson_order, radical, strokes,
              structure, origin, meaning, words_json, sentence, mnemonic,
              confusions_json, quiz_types_json, audio_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(char) DO UPDATE SET
              pinyin = excluded.pinyin,
              radical = excluded.radical,
              strokes = excluded.strokes,
              structure = excluded.structure,
              origin = excluded.origin,
              meaning = excluded.meaning,
              words_json = excluded.words_json,
              sentence = excluded.sentence,
              mnemonic = excluded.mnemonic,
              confusions_json = excluded.confusions_json,
              quiz_types_json = excluded.quiz_types_json,
              audio_key = excluded.audio_key
            """,
            (
                char,
                row.get("pinyin", ""),
                row.get("lesson_id", ""),
                row.get("lesson", ""),
                int(row.get("lesson_order") or 0),
                row.get("radical", ""),
                int(row.get("strokes") or 0),
                row.get("structure", ""),
                row.get("origin", ""),
                row.get("meaning", ""),
                json.dumps(words, ensure_ascii=False),
                row.get("sentence", ""),
                row.get("mnemonic", ""),
                json.dumps(confusions, ensure_ascii=False),
                json.dumps(quiz_types, ensure_ascii=False),
                row.get("audio_key", ""),
            ),
        )


def _seed_literacy(conn: sqlite3.Connection) -> None:
    """导入「幼儿识字 1300」：只补缺的字，不覆盖课内 688 字的内容。

    CSV 里已有字的拼音等字段留空；缺的字带完整卡片数据。顺序写入
    literacy_entries，供认字模块作为独立范围使用。
    """
    if not LITERACY_CSV_PATH.exists():
        return

    with LITERACY_CSV_PATH.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != 1300:
        raise ValueError(f"幼儿识字表应有 1300 行，实际 {len(rows)} 行")

    seen: set[str] = set()
    for row in rows:
        char = (row.get("char") or "").strip()
        if not char:
            continue
        if char in seen:
            raise ValueError(f"幼儿识字表里有重复字：{char}")
        seen.add(char)
        order = int(row.get("sort_order") or 0)
        conn.execute(
            """
            INSERT INTO literacy_entries(char, sort_order) VALUES (?, ?)
            ON CONFLICT(char) DO UPDATE SET sort_order = excluded.sort_order
            """,
            (char, order),
        )

        if not (row.get("pinyin") or "").strip():
            continue
        words = [w.strip() for w in (row.get("words") or "").split("|") if w.strip()]
        quiz_types = [q.strip() for q in (row.get("quiz_types") or "").split("|") if q.strip()]
        conn.execute(
            """
            INSERT INTO characters (
              char, pinyin, lesson_id, lesson, lesson_order, radical, strokes,
              structure, origin, meaning, words_json, sentence, mnemonic,
              confusions_json, quiz_types_json, audio_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(char) DO UPDATE SET
              pinyin = excluded.pinyin,
              radical = excluded.radical,
              strokes = excluded.strokes,
              meaning = excluded.meaning,
              words_json = excluded.words_json,
              quiz_types_json = excluded.quiz_types_json,
              audio_key = excluded.audio_key
            WHERE characters.lesson_id = 'literacy'
            """,
            (
                char,
                row.get("pinyin", ""),
                "literacy",
                "幼儿识字 1300",
                order,
                row.get("radical", ""),
                int(row.get("strokes") or 0),
                "",
                "",
                row.get("meaning", ""),
                json.dumps(words, ensure_ascii=False),
                "",
                "",
                "[]",
                json.dumps(quiz_types or ["pinyin", "audio"], ensure_ascii=False),
                row.get("audio_key", ""),
            ),
        )

    missing = conn.execute(
        """
        SELECT l.char FROM literacy_entries l
        LEFT JOIN characters c ON c.char = l.char
        WHERE c.char IS NULL
        """
    ).fetchall()
    if missing:
        raise ValueError(f"幼儿识字表有 {len(missing)} 个字没有内容：{missing[0]['char']}")


def _seed_progress(conn: sqlite3.Connection) -> None:
    """给内容库里每个字补一行进度（已有进度不动）。"""
    conn.execute(
        "INSERT OR IGNORE INTO char_progress(char) SELECT char FROM content.characters"
    )


def _ensure_settings(conn: sqlite3.Connection) -> None:
    ts = now_iso()
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings(key, value_json, updated_at) VALUES (?, ?, ?)",
            (key, json.dumps(value, ensure_ascii=False), ts),
        )


def get_settings(conn: sqlite3.Connection) -> dict[str, Any]:
    result = dict(DEFAULT_SETTINGS)
    for row in conn.execute("SELECT key, value_json FROM settings"):
        try:
            result[row["key"]] = json.loads(row["value_json"])
        except json.JSONDecodeError:
            pass
    return result


def update_settings(conn: sqlite3.Connection, values: dict[str, Any]) -> dict[str, Any]:
    ts = now_iso()
    allowed = set(DEFAULT_SETTINGS)
    for key, value in values.items():
        if key not in allowed or value is None:
            continue
        conn.execute(
            """
            INSERT INTO settings(key, value_json, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json,
                                           updated_at = excluded.updated_at
            """,
            (key, json.dumps(value, ensure_ascii=False), ts),
        )
    conn.commit()
    return get_settings(conn)


def _checkpoint(path: Path) -> None:
    if not path.exists():
        return
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA wal_checkpoint(FULL)")
    finally:
        conn.close()


def checkpoint_for_backup() -> None:
    _checkpoint(STATS_DB_PATH)


def checkpoint_content_for_backup() -> None:
    _checkpoint(CONTENT_DB_PATH)
