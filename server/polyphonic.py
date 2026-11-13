"""常见多音字补充数据。

教材里标注了不同读音的字由 curriculum_items 动态生成；这个文件只补
「教材没有标、但一年级常用」的多音字。格式：

    char,readings
    地,dì:di4:大地|de:de5:慢慢地

readings 用 | 分隔，每项是「拼音:音频key:例词」。
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "polyphonic.csv"


def list_common_polyphonic() -> list[dict[str, Any]]:
    if not DATA_PATH.exists():
        return []

    items: list[dict[str, Any]] = []
    with DATA_PATH.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            char = (row.get("char") or "").strip()
            readings: list[dict[str, Any]] = []
            for part in (row.get("readings") or "").split("|"):
                bits = [bit.strip() for bit in part.split(":")]
                if len(bits) != 3:
                    continue
                pinyin, audio_key, word = bits
                if not (pinyin and audio_key and word):
                    continue
                readings.append(
                    {
                        "pinyin": pinyin,
                        "audio_key": audio_key,
                        "contexts": [word],
                    }
                )
            if char and len(readings) >= 2:
                items.append({"char": char, "readings": readings})
    return items
