#!/usr/bin/env python3
"""校验 data/families.csv：字族里的字都在 688 字表内、没有重复。"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAMILIES = ROOT / "data" / "families.csv"
CHARS = ROOT / "data" / "characters.csv"


def main() -> int:
    known: set[str] = set()
    with CHARS.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            known.add(row["char"])

    errors: list[str] = []
    seen: set[str] = set()
    count = 0
    with FAMILIES.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            family = (row.get("family") or "").strip()
            members = [m.strip() for m in (row.get("members") or "").split("|") if m.strip()]
            count += 1
            if not family or len(members) < 3:
                errors.append(f"字族「{family or '?'}」至少要有 3 个字")
                continue
            if family in seen:
                errors.append(f"字族「{family}」重复")
            seen.add(family)
            missing = [m for m in members if m not in known]
            if missing:
                errors.append(f"字族「{family}」不在 688 字表内：{''.join(missing)}")
            if len(set(members)) != len(members):
                errors.append(f"字族「{family}」有重复字")

    print(f"字族 {count} 组，错误 {len(errors)} 个")
    for line in errors:
        print("  [错误]", line)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
