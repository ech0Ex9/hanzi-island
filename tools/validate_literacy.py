#!/usr/bin/env python3
"""校验「幼儿识字 1300」：CSV 完整性、数据库落库、课内 / 拓展边界。

用法：python3 tools/validate_literacy.py
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server.db import LITERACY_CSV_PATH, get_db  # noqa: E402

EXPECTED_TOTAL = 1300
EXPECTED_NEW = 636
EXPECTED_TEXTBOOK = 664
TTS_FALLBACK_CHARS = {"修", "休", "详", "翔"}
PINYIN_RE = re.compile(r"[a-zA-Zāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜüɡ]")


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    with LITERACY_CSV_PATH.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    check(len(rows) == EXPECTED_TOTAL, f"CSV 应有 {EXPECTED_TOTAL} 行，实际 {len(rows)} 行")
    chars = [row["char"].strip() for row in rows]
    check(len(set(chars)) == len(chars), "CSV 里有重复字")
    check(
        [int(row["sort_order"]) for row in rows] == list(range(1, EXPECTED_TOTAL + 1)),
        "sort_order 不是 1..1300 连续",
    )

    new_rows = [row for row in rows if (row.get("pinyin") or "").strip()]
    check(len(new_rows) == EXPECTED_NEW, f"补充字应有 {EXPECTED_NEW} 个，实际 {len(new_rows)}")
    check(len(rows) - len(new_rows) == EXPECTED_TEXTBOOK, "课内已有字数量不对")
    charset = set(chars)
    no_audio: list[str] = []

    for row in new_rows:
        char = row["char"]
        pinyin = row.get("pinyin", "")
        check(bool(PINYIN_RE.search(pinyin)), f"{char} 缺少有效拼音")
        check(int(row.get("strokes") or 0) > 0, f"{char} 缺少笔画数")
        check(bool((row.get("radical") or "").strip()), f"{char} 缺少部首")
        check(bool((row.get("meaning") or "").strip()), f"{char} 缺少释义")
        words = [w.strip() for w in (row.get("words") or "").split("|") if w.strip()]
        check(bool(words), f"{char} 缺少组词")
        for word in words:
            check(char in word, f"{char} 的组词「{word}」不包含这个字")
            check(all(c in charset for c in word), f"{char} 的组词「{word}」含 1300 表外的字")
        check("pinyin" in (row.get("quiz_types") or ""), f"{char} 题型缺少 pinyin")
        audio_key = (row.get("audio_key") or "").strip()
        if audio_key:
            check(
                (ROOT / "web/assets/audio/pinyin" / f"{audio_key}.mp3").exists(),
                f"{char} 的音频 key 不存在：{audio_key}",
            )
        else:
            no_audio.append(char)
        if "见下" in row.get("meaning", "") or (row.get("meaning") or "").startswith("同"):
            warnings.append(f"{char} 的释义可能需要人工复核：{row.get('meaning')}")

    unexpected_no_audio = sorted(set(no_audio) - TTS_FALLBACK_CHARS)
    check(
        not unexpected_no_audio,
        f"这些补充字没有 mp3 且不在已知 TTS 兜底名单：{''.join(unexpected_no_audio)}",
    )

    with get_db() as conn:
        count = int(conn.execute("SELECT COUNT(*) FROM literacy_entries").fetchone()[0])
        check(count == EXPECTED_TOTAL, f"数据库 literacy_entries 应有 {EXPECTED_TOTAL} 条，实际 {count}")
        missing = conn.execute(
            """
            SELECT l.char FROM literacy_entries l
            LEFT JOIN characters c ON c.char = l.char
            WHERE c.char IS NULL
            """
        ).fetchall()
        check(not missing, f"数据库里有 {len(missing)} 个识字表字缺少 characters 内容")
        missing_progress = conn.execute(
            """
            SELECT l.char FROM literacy_entries l
            LEFT JOIN char_progress p ON p.char = l.char
            WHERE p.char IS NULL
            """
        ).fetchall()
        check(not missing_progress, f"数据库里有 {len(missing_progress)} 个识字表字缺少进度行")
        extras = conn.execute(
            """
            SELECT COUNT(*) FROM literacy_entries l
            WHERE NOT EXISTS (SELECT 1 FROM curriculum_items i WHERE i.char = l.char)
            """
        ).fetchone()[0]
        check(int(extras) == EXPECTED_NEW, f"拓展字应有 {EXPECTED_NEW} 个，实际 {extras}")
        textbook = conn.execute(
            """
            SELECT COUNT(*) FROM literacy_entries l
            WHERE EXISTS (SELECT 1 FROM curriculum_items i WHERE i.char = l.char)
            """
        ).fetchone()[0]
        check(int(textbook) == EXPECTED_TEXTBOOK, f"课内字应有 {EXPECTED_TEXTBOOK} 个，实际 {textbook}")

    print(
        f"幼儿识字 1300：总 {len(rows)} 字，补充 {len(new_rows)} 字，"
        f"音频 {len(new_rows) - len(no_audio)} 字，TTS 兜底 {len(no_audio)} 字，"
        f"错误 {len(errors)} 个，提醒 {len(warnings)} 个"
    )
    for line in errors:
        print("  [错误]", line)
    for line in warnings:
        print("  [提醒]", line)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
