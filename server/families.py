"""字族：同一部件/声旁的字，用来做归类和迁移。

数据源：data/families.csv（family, members 用 | 分隔）。
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "families.csv"


def list_families() -> list[dict[str, Any]]:
    if not DATA_PATH.exists():
        return []

    families: list[dict[str, Any]] = []
    with DATA_PATH.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            family = (row.get("family") or "").strip()
            members = [
                item.strip()
                for item in (row.get("members") or "").split("|")
                if item.strip()
            ]
            if family and members:
                families.append({"family": family, "members": members})
    return families
