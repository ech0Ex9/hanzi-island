#!/usr/bin/env python3
"""校验 data/readings.csv：用字是否都在字表里、篇幅是否合适、单元是否存在。

用法：python3 tools/validate_readings.py
"""

from __future__ import annotations

import csv
import json
import sqlite3
import sys
from pathlib import Path

from pinyin_audio import pinyin_to_audio_key

ROOT = Path(__file__).resolve().parent.parent
READINGS = ROOT / "data" / "readings.csv"
CHARS = ROOT / "data" / "characters.csv"
DB = ROOT / "data" / "content.db"
AUDIO = ROOT / "web" / "assets" / "audio" / "pinyin"

PUNCT = set("，。！？、；：“”‘’（）《》…—·,.!?;:")


def main() -> int:
    if not READINGS.exists():
        print("缺少 data/readings.csv")
        return 1

    known: set[str] = set()
    allowed: dict[str, set[tuple[str, str]]] = {}
    with CHARS.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            char = row["char"]
            known.add(char)
            pinyin = (row.get("pinyin") or "").strip()
            audio_key = (row.get("audio_key") or "").strip()
            if pinyin and audio_key:
                allowed.setdefault(char, set()).add((pinyin, audio_key))

    poly_path = ROOT / "data" / "polyphonic.csv"
    if poly_path.exists():
        with poly_path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                char = (row.get("char") or "").strip()
                for part in (row.get("readings") or "").split("|"):
                    bits = [bit.strip() for bit in part.split(":")]
                    if len(bits) == 3 and all(bits):
                        allowed.setdefault(char, set()).add((bits[0], bits[1]))

    units: set[str] = set()
    if DB.exists():
        conn = sqlite3.connect(DB)
        units = {row[0] for row in conn.execute("SELECT id FROM units")}
        for char, pinyin, audio_key in conn.execute(
            """
            SELECT DISTINCT char, pinyin_override, audio_key_override
            FROM curriculum_items
            WHERE pinyin_override IS NOT NULL AND pinyin_override != ''
              AND audio_key_override IS NOT NULL AND audio_key_override != ''
            """
        ):
            allowed.setdefault(char, set()).add((pinyin, audio_key))
        conn.close()

    errors: list[str] = []
    warnings: list[str] = []

    with READINGS.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    seen_ids: set[str] = set()
    for row in rows:
        rid = (row.get("id") or "").strip()
        title = (row.get("title") or "").strip()
        lines = [s.strip() for s in (row.get("lines") or "").split("|") if s.strip()]
        label = f"{rid or '?'}《{title or '?'}》"

        if not rid or not title:
            errors.append(f"{label}：缺少 id 或标题")
        if rid in seen_ids:
            errors.append(f"{label}：id 重复")
        seen_ids.add(rid)

        unit_id = (row.get("unit_id") or "").strip()
        if units and unit_id not in units:
            errors.append(f"{label}：单元 {unit_id} 不存在")

        if not 2 <= len(lines) <= 4:
            warnings.append(f"{label}：{len(lines)} 句（建议 2–4 句）")

        text = "".join(lines)
        body = [c for c in text if c not in PUNCT]
        if not 20 <= len(body) <= 30:
            warnings.append(f"{label}：正文 {len(body)} 字（建议 20–30 字）")

        missing = sorted({c for c in body if c not in known})
        if missing:
            errors.append(f"{label}：不在 688 字表内的字：{''.join(missing)}")

        raw_pronunciations = (row.get("pronunciations") or "").strip()
        if raw_pronunciations:
            try:
                pronunciations = json.loads(raw_pronunciations)
            except json.JSONDecodeError as exc:
                errors.append(f"{label}：pronunciations 不是合法 JSON（{exc.msg}）")
                continue
            if not isinstance(pronunciations, dict):
                errors.append(f"{label}：pronunciations 应为 JSON 对象")
                continue
            for char, value in pronunciations.items():
                if char not in text:
                    errors.append(f"{label}：多音字标注「{char}」没有出现在正文里")
                    continue
                if not isinstance(value, dict):
                    errors.append(f"{label}：「{char}」的读音标注应为对象")
                    continue
                pinyin = str(value.get("pinyin") or "").strip()
                audio_key = str(value.get("audio_key") or "").strip()
                if not pinyin or not audio_key:
                    errors.append(f"{label}：「{char}」缺少 pinyin 或 audio_key")
                    continue
                if not (AUDIO / f"{audio_key}.mp3").exists():
                    errors.append(f"{label}：「{char}」缺少音频 {audio_key}.mp3")
                if pinyin_to_audio_key(pinyin) != audio_key:
                    errors.append(
                        f"{label}：「{char}」拼音 {pinyin} 与音频 {audio_key} 不一致"
                    )
                if allowed.get(char) and (pinyin, audio_key) not in allowed[char]:
                    errors.append(
                        f"{label}：「{char}」的读音 {pinyin}/{audio_key} 不在字表、多音字表或教材标注里"
                    )

    print(f"短文 {len(rows)} 篇，错误 {len(errors)} 个，提醒 {len(warnings)} 个")
    for line in errors:
        print("  [错误]", line)
    for line in warnings:
        print("  [提醒]", line)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
