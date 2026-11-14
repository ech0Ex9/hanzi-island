"""诗岛：一年级适读古诗。

数据源：data/poems.csv
列：id,title,author,dynasty,genre,theme,difficulty,lines,pinyin,
    translation,notes,sort_order

lines / pinyin 用 | 分行；pinyin 每行按空格分音节，和去掉标点后的汉字一一对应。
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Any

from .db import now_iso, today_str

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "poems.csv"
PUNCT = set("，。！？、；：“”‘’（）《》…— ")


def _split_lines(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split("|") if part.strip()]


def _load_poems() -> list[dict[str, Any]]:
    if not DATA_PATH.exists():
        return []
    items: list[dict[str, Any]] = []
    with DATA_PATH.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            poem_id = (row.get("id") or "").strip()
            if not poem_id:
                continue
            lines = _split_lines(row.get("lines") or "")
            pinyin_lines = [part.split() for part in _split_lines(row.get("pinyin") or "")]
            audio_key_lines = [
                part.split() for part in _split_lines(row.get("audio_keys") or "")
            ]
            if len(lines) != len(pinyin_lines):
                raise ValueError(f"{poem_id}：诗句和拼音行数不一致")
            if audio_key_lines and len(audio_key_lines) != len(lines):
                raise ValueError(f"{poem_id}：诗句和音频 key 行数不一致")
            for line, syllables in zip(lines, pinyin_lines):
                chars = [char for char in line if char not in PUNCT]
                if len(chars) != len(syllables):
                    raise ValueError(
                        f"{poem_id}：这一句有 {len(chars)} 个字，但有 {len(syllables)} 个拼音"
                    )
            for index, syllables in enumerate(pinyin_lines):
                keys = audio_key_lines[index] if index < len(audio_key_lines) else []
                if keys and len(keys) != len(syllables):
                    raise ValueError(f"{poem_id}：第 {index + 1} 句拼音和音频 key 数量不一致")
            items.append(
                {
                    "id": poem_id,
                    "title": (row.get("title") or "").strip(),
                    "author": (row.get("author") or "").strip(),
                    "dynasty": (row.get("dynasty") or "").strip(),
                    "genre": (row.get("genre") or "").strip(),
                    "themes": _split_lines(row.get("theme") or ""),
                    "difficulty": int(row.get("difficulty") or 1),
                    "lines": lines,
                    "pinyin_lines": pinyin_lines,
                    "audio_key_lines": audio_key_lines,
                    "translation": (row.get("translation") or "").strip(),
                    "notes": _split_lines(row.get("notes") or ""),
                    "sort_order": int(row.get("sort_order") or 0),
                    "read": False,
                    "read_count": 0,
                    "last_read": None,
                }
            )
    items.sort(key=lambda item: (item["sort_order"], item["title"]))
    return items


def _read_stats(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT poem_id, COUNT(*) AS reads, MAX(ts) AS last_read
        FROM poem_reads
        WHERE completed = 1
        GROUP BY poem_id
        """
    ).fetchall()
    return {
        row["poem_id"]: {
            "read_count": int(row["reads"]),
            "last_read": row["last_read"],
        }
        for row in rows
    }


def list_poems(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    stats = _read_stats(conn)
    items = _load_poems()
    for item in items:
        record = stats.get(item["id"])
        if record:
            item["read"] = True
            item["read_count"] = record["read_count"]
            item["last_read"] = record["last_read"]
    return items


def get_poem(conn: sqlite3.Connection, poem_id: str) -> dict[str, Any] | None:
    return next((item for item in list_poems(conn) if item["id"] == poem_id), None)


def summary(conn: sqlite3.Connection) -> dict[str, Any]:
    items = list_poems(conn)
    return {
        "total": len(items),
        "read": sum(1 for item in items if item["read"]),
    }


def mark_read(conn: sqlite3.Connection, poem_id: str) -> dict[str, Any]:
    poem = get_poem(conn, poem_id)
    if poem is None:
        raise KeyError("没有这首诗")
    conn.execute(
        """
        INSERT INTO poem_reads(poem_id, ts, local_date, mode, completed)
        VALUES (?, ?, ?, 'read', 1)
        """,
        (poem_id, now_iso(), today_str()),
    )
    conn.commit()
    poem = get_poem(conn, poem_id)
    return {"poem": poem, "summary": summary(conn)}
