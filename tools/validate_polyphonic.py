#!/usr/bin/env python3
"""校验 data/polyphonic.csv：字在 688 字表内、至少两个读音、音频齐全。"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from pinyin_audio import pinyin_to_audio_key

ROOT = Path(__file__).resolve().parent.parent
POLY = ROOT / "data" / "polyphonic.csv"
CHARS = ROOT / "data" / "characters.csv"
AUDIO = ROOT / "web" / "assets" / "audio" / "pinyin"


def main() -> int:
    known: set[str] = set()
    with CHARS.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            known.add(row["char"])

    errors: list[str] = []
    count = 0
    with POLY.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            char = (row.get("char") or "").strip()
            count += 1
            if char not in known:
                errors.append(f"{char or '?'}：不在 688 字表内")
                continue
            readings = [part.strip() for part in (row.get("readings") or "").split("|") if part.strip()]
            if len(readings) < 2:
                errors.append(f"{char}：少于两个读音")
            seen: set[str] = set()
            for part in readings:
                bits = [bit.strip() for bit in part.split(":")]
                if len(bits) != 3 or not all(bits):
                    errors.append(f"{char}：读音格式应为「拼音:音频key:例词」→ {part}")
                    continue
                pinyin, audio_key, word = bits
                if pinyin in seen:
                    errors.append(f"{char}：读音重复 {pinyin}")
                seen.add(pinyin)
                if not (AUDIO / f"{audio_key}.mp3").exists():
                    errors.append(f"{char}：缺少音频 {audio_key}.mp3")
                if pinyin_to_audio_key(pinyin) != audio_key:
                    errors.append(
                        f"{char}：拼音 {pinyin} 与音频 {audio_key} 不一致（应为 {pinyin_to_audio_key(pinyin)}）"
                    )
                if char not in word:
                    errors.append(f"{char}：例词「{word}」不含这个字")

    print(f"多音字补充 {count} 个，错误 {len(errors)} 个")
    for line in errors:
        print("  [错误]", line)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
