#!/usr/bin/env python3
"""检查内容与课程位置（v2）。

检查两类数据：
1. data/characters.csv —— 字的内容（P0 起不再含 lesson 列）。
2. data/curriculum/*.csv —— 课程位置（书/单元/课文/字位置 + 多音字 override）。

交叉检查：
- 位置有字但 characters.csv 没内容 → 提醒（P1/P2 补内容），不算错误。
- 内容有字但没有任何课程位置 → 提醒。
- audio_key / audio_key_override 对应的 mp3 必须存在。

用法：
    python3 tools/validate_content.py
"""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

from pinyin_audio import pinyin_to_audio_key

ROOT = Path(__file__).resolve().parent.parent
CONTENT_CSV = ROOT / "data" / "characters.csv"
CURRICULUM_DIR = ROOT / "data" / "curriculum"
AUDIO_DIR = ROOT / "web" / "assets" / "audio" / "pinyin"

CONTENT_COLUMNS = [
    "char", "pinyin", "radical", "strokes", "structure", "origin", "meaning",
    "words", "sentence", "mnemonic", "confusions", "quiz_types", "audio_key",
]
POSITION_COLUMNS = [
    "book_id", "unit_no", "unit_title", "unit_kind", "lesson_no", "lesson_title",
    "lesson_kind", "lesson_order", "item_order", "char", "pinyin_override",
    "audio_key_override", "meaning_override", "words_override", "sentence_override",
    "mnemonic_override",
]
ALLOWED_QUIZ = {"audio", "pinyin", "word", "cloze"}
# 教材官方标注：一上 280 字（本来源按课文列得 279，差异字待课本核实）、一下 410。
EXPECTED_UNIQUE = {"1a": 280, "1b": 410}

TONE_RE = re.compile(r"[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]")


def check_content() -> tuple[list[str], list[str], set[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    with CONTENT_CSV.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    if not rows:
        return ["characters.csv 是空的"], warnings, set()

    missing = [key for key in CONTENT_COLUMNS if key not in rows[0]]
    extra = [key for key in rows[0] if key not in CONTENT_COLUMNS]
    if missing:
        errors.append(f"characters.csv 缺少列：{', '.join(missing)}")
    if extra:
        errors.append(f"characters.csv 有多余列（课程位置应放 data/curriculum/）：{', '.join(extra)}")

    chars = [row.get("char", "").strip() for row in rows]
    duplicates = [char for char, count in Counter(chars).items() if count > 1 and char]
    if duplicates:
        errors.append(f"重复字：{'、'.join(duplicates)}")

    for row in rows:
        char = (row.get("char") or "").strip()
        if not char:
            errors.append("有一行没有字")
            continue
        if len(char) != 1:
            errors.append(f"「{char}」不是单字")

        pinyin = (row.get("pinyin") or "").strip()
        if not pinyin:
            errors.append(f"{char}：没有拼音")
        elif not TONE_RE.search(pinyin):
            warnings.append(f"{char}：拼音没有声调符号（{pinyin}）")

        words = [w.strip() for w in (row.get("words") or "").split("|") if w.strip()]
        if not words:
            errors.append(f"{char}：没有组词")
        elif len(words) < 2:
            warnings.append(f"{char}：组词少于 2 个")
        for word in words:
            if char not in word:
                warnings.append(f"{char}：组词「{word}」不含目标字")

        sentence = (row.get("sentence") or "").strip()
        if not sentence:
            warnings.append(f"{char}：没有例句")
        elif sentence.count(char) != 1:
            warnings.append(f"{char}：例句里目标字出现 {sentence.count(char)} 次（填空题要求恰好 1 次）")

        if not (row.get("meaning") or "").strip():
            warnings.append(f"{char}：没有释义")
        if not (row.get("mnemonic") or "").strip():
            warnings.append(f"{char}：没有记忆口诀")

        confusions = [c.strip() for c in (row.get("confusions") or "").split("|") if c.strip()]
        if len(confusions) < 2:
            warnings.append(f"{char}：形近字少于 2 个")
        for confusion in confusions:
            if len(confusion) != 1:
                errors.append(f"{char}：形近字「{confusion}」不是单字")

        quiz_types = [q.strip() for q in (row.get("quiz_types") or "").split("|") if q.strip()]
        unknown = set(quiz_types) - ALLOWED_QUIZ
        if unknown:
            errors.append(f"{char}：未知题型 {', '.join(sorted(unknown))}")
        if not quiz_types:
            errors.append(f"{char}：没有题型")

        audio_key = (row.get("audio_key") or "").strip()
        if not audio_key:
            errors.append(f"{char}：没有 audio_key")
        elif not (AUDIO_DIR / f"{audio_key}.mp3").exists():
            errors.append(f"{char}：音频 {audio_key}.mp3 不存在")
        if pinyin and audio_key:
            expected_audio = pinyin_to_audio_key(pinyin)
            if expected_audio != audio_key:
                errors.append(
                    f"{char}：拼音 {pinyin} 与 audio_key {audio_key} 不一致（应为 {expected_audio}）"
                )

    return errors, warnings, {c for c in chars if c}


def check_positions() -> tuple[list[str], list[str], dict[str, set[str]]]:
    errors: list[str] = []
    warnings: list[str] = []
    by_book: dict[str, set[str]] = {}

    paths = sorted(CURRICULUM_DIR.glob("*.csv"))
    if not paths:
        return [f"找不到课程位置文件：{CURRICULUM_DIR}/*.csv"], warnings, by_book

    for path in paths:
        book_id = path.stem
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            errors.append(f"{path.name} 是空的")
            continue
        missing = [key for key in POSITION_COLUMNS if key not in rows[0]]
        if missing:
            errors.append(f"{path.name} 缺少列：{', '.join(missing)}")
            continue

        seen_lesson_char: set[tuple[str, str]] = set()
        lesson_orders: dict[str, list[int]] = {}
        book_chars: set[str] = by_book.setdefault(book_id, set())

        for index, row in enumerate(rows, start=2):
            char = (row.get("char") or "").strip()
            lesson_key = f"{row.get('unit_no')}-{row.get('lesson_order')}"
            if not char:
                errors.append(f"{path.name} 第 {index} 行没有字")
                continue
            book_chars.add(char)
            if len(char) != 1:
                errors.append(f"{path.name} 第 {index} 行「{char}」不是单字")
            key = (lesson_key, char)
            if key in seen_lesson_char:
                errors.append(f"{path.name}：{lesson_key} 课里「{char}」重复出现")
            seen_lesson_char.add(key)

            try:
                order = int(row.get("item_order") or 0)
            except ValueError:
                errors.append(f"{path.name} 第 {index} 行 item_order 不是整数")
                order = 0
            lesson_orders.setdefault(lesson_key, []).append(order)

            pinyin_override = (row.get("pinyin_override") or "").strip()
            audio_override = (row.get("audio_key_override") or "").strip()
            if audio_override and not pinyin_override:
                errors.append(f"{path.name} {lesson_key} {char}：有 audio_key_override 但没有 pinyin_override")
            if pinyin_override and not TONE_RE.search(pinyin_override):
                warnings.append(
                    f"{path.name} {lesson_key} {char}：override 拼音没有声调符号（{pinyin_override}）"
                )
            if audio_override and not (AUDIO_DIR / f"{audio_override}.mp3").exists():
                errors.append(f"{path.name} {lesson_key} {char}：override 音频 {audio_override}.mp3 不存在")

        for lesson_key, orders in lesson_orders.items():
            if len(orders) != len(set(orders)):
                errors.append(f"{path.name}：{lesson_key} 的 item_order 有重复")

        expected = EXPECTED_UNIQUE.get(book_id)
        if expected and len(book_chars) != expected:
            warnings.append(
                f"{path.name}：不同字 {len(book_chars)} 个，教材官方标注 {expected} 个（差异字需对照课本核实）"
            )

    return errors, warnings, by_book


def main() -> int:
    content_errors, content_warnings, content_chars = check_content()
    position_errors, position_warnings, position_chars = check_positions()

    # 交叉检查：位置有字但没内容 → 提醒（不算错误，P1/P2 补内容）
    missing_content: dict[str, list[str]] = {}
    for book_id, chars in position_chars.items():
        missing = sorted(chars - content_chars)
        if missing:
            missing_content[book_id] = missing
    for book_id, missing in missing_content.items():
        sample = "".join(missing[:20])
        position_warnings.append(
            f"{book_id}：{len(missing)} 个位置的字还没有内容（样例：{sample}{'…' if len(missing) > 20 else ''}）"
        )
    orphans = sorted(content_chars - set().union(*position_chars.values()) if position_chars else content_chars)
    if orphans:
        content_warnings.append(f"这些字在课程位置表里找不到：{''.join(orphans)}")

    errors = content_errors + position_errors
    warnings = content_warnings + position_warnings

    print(f"内容：{len(content_chars)} 个字；课程位置："
          + "，".join(f"{book} {len(chars)} 个不同字" for book, chars in sorted(position_chars.items())))
    print(f"错误 {len(errors)} 个，提醒 {len(warnings)} 个")
    for item in errors:
        print("  [错误]", item)
    for item in warnings:
        print("  [提醒]", item)
    if errors:
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
