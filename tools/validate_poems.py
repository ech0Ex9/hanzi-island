#!/usr/bin/env python3
"""校验诗岛内容：10 首试点、拼音分行、音节数、音频可用性。"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "poems.csv"
AUDIO = ROOT / "web" / "assets" / "audio" / "pinyin"
PUNCT = set("，。！？、；：“”‘’（）《》…— ")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pinyin_audio import pinyin_to_audio_key  # noqa: E402


def main() -> int:
    if not CSV_PATH.exists():
        print("缺少 data/poems.csv")
        return 1
    with CSV_PATH.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    errors: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()
    missing_audio: set[str] = set()

    for row in rows:
        poem_id = (row.get("id") or "").strip()
        if not poem_id:
            errors.append("有一行没有 id")
            continue
        if poem_id in seen:
            errors.append(f"{poem_id}：id 重复")
        seen.add(poem_id)
        for field in ("title", "author", "dynasty", "translation"):
            if not (row.get(field) or "").strip():
                errors.append(f"{poem_id}：缺少 {field}")
        lines = [part.strip() for part in (row.get("lines") or "").split("|") if part.strip()]
        pinyin_lines = [
            part.split() for part in (row.get("pinyin") or "").split("|") if part.strip()
        ]
        audio_key_lines = [
            part.split() for part in (row.get("audio_keys") or "").split("|") if part.strip()
        ]
        if not lines:
            errors.append(f"{poem_id}：没有诗句")
            continue
        if len(lines) != len(pinyin_lines):
            errors.append(f"{poem_id}：诗句 {len(lines)} 行，拼音 {len(pinyin_lines)} 行")
            continue
        if audio_key_lines and len(audio_key_lines) != len(lines):
            errors.append(f"{poem_id}：诗句 {len(lines)} 行，音频 key {len(audio_key_lines)} 行")
            continue
        for index, (line, syllables) in enumerate(zip(lines, pinyin_lines), 1):
            chars = [char for char in line if char not in PUNCT]
            if len(chars) != len(syllables):
                errors.append(
                    f"{poem_id} 第 {index} 句：{len(chars)} 个字，{len(syllables)} 个拼音"
                )
            keys = audio_key_lines[index - 1] if index - 1 < len(audio_key_lines) else []
            if keys and len(keys) != len(syllables):
                errors.append(
                    f"{poem_id} 第 {index} 句：{len(syllables)} 个拼音，{len(keys)} 个音频 key"
                )
            for syllable_index, pinyin in enumerate(syllables):
                key = pinyin_to_audio_key(pinyin)
                if not (AUDIO / f"{key}.mp3").exists():
                    missing_audio.add(f"{pinyin}/{key}")
                if keys and keys[syllable_index] != key:
                    errors.append(
                        f"{poem_id} 第 {index} 句：{pinyin} 的音频 key 应为 {key}，实际 {keys[syllable_index]}"
                    )
        themes = [part for part in (row.get("theme") or "").split("|") if part.strip()]
        if not themes:
            errors.append(f"{poem_id}：没有主题")
        try:
            difficulty = int(row.get("difficulty") or 0)
            if difficulty not in (1, 2, 3):
                errors.append(f"{poem_id}：难度应为 1–3")
        except ValueError:
            errors.append(f"{poem_id}：难度不是数字")

    if missing_audio:
        warnings.append(
            "以下音节没有 mp3，会退回系统 TTS："
            + "、".join(sorted(missing_audio))
        )

    print(f"诗岛：{len(rows)} 首诗，错误 {len(errors)} 个，提醒 {len(warnings)} 个")
    for line in errors:
        print("  [错误]", line)
    for line in warnings:
        print("  [提醒]", line)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
