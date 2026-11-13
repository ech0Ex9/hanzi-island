#!/usr/bin/env python3
"""把一批新字内容追加进 data/characters.csv。

内容 JSON 格式（list）：
    [{"char":"川","radical":"川","strokes":3,"structure":"独体","origin":"象形",
      "meaning":"…","words":"山川|河川","sentence":"…","mnemonic":"…",
      "confusions":"州|三"}, …]

拼音和 audio_key 从 data/sources/ 的官方识字表 JSON 的第一个位置取
（教材注音为准），不用手写。自动在一上 / 一下两份源里查找。

用法：
    python3 tools/append_content.py <batch.json>
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "characters.csv"
SOURCE_JSONS = [
    ROOT / "data" / "sources" / "一年级上册-识字表-2024新版.json",
    ROOT / "data" / "sources" / "一年级下册-识字表-2025新版-官方.json",
]
AUDIO_DIR = ROOT / "web" / "assets" / "audio" / "pinyin"

FIELDS = ["radical", "strokes", "structure", "origin", "meaning", "words",
          "sentence", "mnemonic", "confusions"]
QUIZ_TYPES = "audio|pinyin|word|cloze"


def first_reading() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for path in SOURCE_JSONS:
        if not path.exists():
            continue
        recs = json.loads(path.read_text(encoding="utf-8"))["records"]
        for rec in recs:
            ch = rec["char"]
            if ch not in out:
                out[ch] = {"pinyin": rec["pinyin"], "audio_key": rec["syllable"]}
    return out


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    items = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    readings = first_reading()

    with CSV_PATH.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
        existing = {r["char"] for r in rows}
        fieldnames = list(rows[0].keys()) if rows else list(csv.DictReader(f).fieldnames)

    added, skipped = 0, 0
    with CSV_PATH.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        for item in items:
            char = item["char"].strip()
            if char in existing:
                print(f"  [跳过] {char} 已存在")
                skipped += 1
                continue
            missing = [k for k in FIELDS if not str(item.get(k, "")).strip()]
            if missing:
                print(f"  [错误] {char} 缺字段：{', '.join(missing)}")
                return 1
            reading = readings.get(char)
            if reading is None:
                print(f"  [错误] {char} 不在 2024 上册识字表里")
                return 1
            if not (AUDIO_DIR / f"{reading['audio_key']}.mp3").exists():
                print(f"  [错误] {char} 音频缺失：{reading['audio_key']}.mp3")
                return 1
            row = {
                "char": char,
                "pinyin": reading["pinyin"],
                "audio_key": reading["audio_key"],
                "quiz_types": QUIZ_TYPES,
            }
            for key in FIELDS:
                row[key] = str(item[key]).strip()
            writer.writerow(row)
            existing.add(char)
            added += 1
    print(f"追加 {added} 个字，跳过 {skipped} 个；现有 {len(existing)} 个字")
    return 0


if __name__ == "__main__":
    sys.exit(main())
