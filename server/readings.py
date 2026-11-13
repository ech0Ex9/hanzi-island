"""读一读：短文 / 儿歌数据。

数据源：data/readings.csv
列：id, book_id, unit_id, title, lines（多句用 | 分隔）
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "readings.csv"


def list_readings() -> list[dict[str, Any]]:
    if not DATA_PATH.exists():
        return []

    items: list[dict[str, Any]] = []
    with DATA_PATH.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            lines = [line.strip() for line in (row.get("lines") or "").split("|") if line.strip()]
            if not lines:
                continue
            pronunciations: dict[str, dict[str, str]] = {}
            raw_pronunciations = (row.get("pronunciations") or "").strip()
            if raw_pronunciations:
                try:
                    data = json.loads(raw_pronunciations)
                except json.JSONDecodeError:
                    data = {}
                if isinstance(data, dict):
                    for char, value in data.items():
                        if not isinstance(value, dict):
                            continue
                        pinyin = str(value.get("pinyin") or "").strip()
                        audio_key = str(value.get("audio_key") or "").strip()
                        if char and pinyin and audio_key:
                            pronunciations[char] = {"pinyin": pinyin, "audio_key": audio_key}
            items.append(
                {
                    "id": (row.get("id") or "").strip(),
                    "book_id": (row.get("book_id") or "").strip(),
                    "unit_id": (row.get("unit_id") or "").strip(),
                    "title": (row.get("title") or "").strip(),
                    "lines": lines,
                    "text": "".join(lines),
                    "pronunciations": pronunciations,
                }
            )
    return items
