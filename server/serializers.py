"""把 sqlite3.Row 转成前端好用的 dict。"""

from __future__ import annotations

import json
from typing import Any


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        data = json.loads(value)
        return [str(x) for x in data] if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def progress_to_dict(row: Any) -> dict[str, Any]:
    return {
        "box": row["box"],
        "due_at": row["due_at"],
        "exposures": row["exposures"],
        "attempts": row["attempts"],
        "correct": row["correct"],
        "wrong": row["wrong"],
        "streak": row["streak"],
        "mastery": row["mastery"],
        "first_seen_at": row["first_seen_at"],
        "last_seen_at": row["last_seen_at"],
    }


def char_to_dict(row: Any) -> dict[str, Any]:
    data = {
        "char": row["char"],
        "pinyin": row["pinyin"],
        "lesson_id": row["lesson_id"],
        "lesson": row["lesson"],
        "lesson_order": row["lesson_order"],
        "radical": row["radical"],
        "strokes": row["strokes"],
        "structure": row["structure"],
        "origin": row["origin"],
        "meaning": row["meaning"],
        "words": _json_list(row["words_json"]),
        "sentence": row["sentence"],
        "mnemonic": row["mnemonic"],
        "confusions": _json_list(row["confusions_json"]),
        "quiz_types": _json_list(row["quiz_types_json"]),
        "audio_key": row["audio_key"],
    }
    keys = row.keys()
    if "box" in keys:
        data["progress"] = progress_to_dict(row)
    return data
