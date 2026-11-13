#!/usr/bin/env python3
"""从 mp3-chinese-pinyin-sound 下载当前字表需要的拼音音节音频。

源仓库：https://github.com/davinfifield/mp3-chinese-pinyin-sound
许可证：Unlicense（public domain）

课内字表 characters.csv 和拓展字表 literacy_1300.csv 都会读取：
优先用行里的 audio_key，没有时按 pinyin 推导音节 key。这样新增拓展字后
直接重跑本脚本即可补齐，不会再只下载课内 688 字用到的音节。

用法：
    python3 tools/fetch_pinyin_audio.py
    python3 tools/fetch_pinyin_audio.py --force
"""

from __future__ import annotations

import argparse
import csv
import sys
import urllib.error
import urllib.request
from pathlib import Path

from pinyin_audio import pinyin_to_audio_key

ROOT = Path(__file__).resolve().parent.parent
CSV_PATHS = [
    ROOT / "data" / "characters.csv",
    ROOT / "data" / "literacy_1300.csv",
]
OUT_DIR = ROOT / "web" / "assets" / "audio" / "pinyin"
BASE_URL = "https://raw.githubusercontent.com/davinfifield/mp3-chinese-pinyin-sound/master/mp3"
# 上游音频库确实没有这两个音节，对应字用系统 TTS，不算下载失败。
KNOWN_UNAVAILABLE = {"xiu1", "xiang2"}


def download(key: str, force: bool) -> tuple[str, int]:
    target = OUT_DIR / f"{key}.mp3"
    if target.exists() and not force and target.stat().st_size > 1000:
        return "skip", target.stat().st_size

    url = f"{BASE_URL}/{key}.mp3"
    request = urllib.request.Request(url, headers={"User-Agent": "hanzi-island/0.1"})
    with urllib.request.urlopen(request, timeout=20) as response:
        data = response.read()
    if len(data) < 1000 or not data.startswith(b"ID3"):
        raise ValueError(f"{key}: 下载内容不像 MP3（{len(data)} bytes）")
    tmp = target.with_suffix(".mp3.tmp")
    tmp.write_bytes(data)
    tmp.replace(target)
    return "download", len(data)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="重新下载已有文件")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    keys = []
    for csv_path in CSV_PATHS:
        if not csv_path.exists():
            continue
        with csv_path.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        for row in rows:
            key = (row.get("audio_key") or "").strip()
            if not key:
                pinyin = (row.get("pinyin") or "").strip()
                key = pinyin_to_audio_key(pinyin) if pinyin else ""
            if key and key not in keys:
                keys.append(key)

    total = 0
    failures = []
    fallback = []
    for key in keys:
        try:
            action, size = download(key, args.force)
            total += size
            print(f"  {action:8} {key}.mp3 ({size} bytes)")
        except urllib.error.HTTPError as exc:
            if key in KNOWN_UNAVAILABLE and exc.code == 404:
                fallback.append(key)
                print(f"  TTS      {key}.mp3（上游没有，改用系统 TTS）")
            else:
                failures.append((key, str(exc)))
                print(f"  FAIL     {key}: {exc}")
        except (urllib.error.URLError, ValueError) as exc:
            failures.append((key, str(exc)))
            print(f"  FAIL     {key}: {exc}")

    print(f"\n完成 {len(keys) - len(failures)} / {len(keys)}，共 {total / 1024:.0f} KB")
    if fallback:
        print(f"系统 TTS 兜底：{'、'.join(fallback)}")
    if failures:
        print("失败：")
        for key, reason in failures:
            print(f"  {key}: {reason}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
