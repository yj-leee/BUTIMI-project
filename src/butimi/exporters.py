"""VehicleListing 목록을 CSV / 엑셀로 내보내기.

- CSV : 표준 라이브러리만 사용. utf-8-sig(BOM) 로 저장해 엑셀에서 한글이 깨지지 않게 함.
- XLSX: openpyxl 사용(설치돼 있을 때만).
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Sequence

from .models import VehicleListing


def to_csv(
    listings: Sequence[VehicleListing],
    path: str | Path,
    include_raw: bool = False,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = VehicleListing.export_columns(include_raw=include_raw)

    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for item in listings:
            row = item.to_row(include_raw=include_raw)
            if include_raw:
                row["raw"] = _json_compact(row.get("raw"))
            writer.writerow(row)
    return path


def to_xlsx(
    listings: Sequence[VehicleListing],
    path: str | Path,
    include_raw: bool = False,
    sheet_name: str = "vehicles",
) -> Path:
    try:
        from openpyxl import Workbook
    except ImportError as exc:  # pragma: no cover - 의존성 안내
        raise RuntimeError(
            "엑셀(.xlsx) 내보내기에는 openpyxl 이 필요합니다. "
            "`pip install openpyxl` 후 다시 시도하세요."
        ) from exc

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = VehicleListing.export_columns(include_raw=include_raw)

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31]  # 엑셀 시트명 31자 제한
    ws.append(columns)
    for item in listings:
        row = item.to_row(include_raw=include_raw)
        if include_raw:
            row["raw"] = _json_compact(row.get("raw"))
        ws.append([row.get(col, "") for col in columns])

    # 헤더 고정 + 대략적인 열 너비
    ws.freeze_panes = "A2"
    for idx, col in enumerate(columns, start=1):
        ws.column_dimensions[_col_letter(idx)].width = min(max(len(col) + 2, 12), 40)

    wb.save(path)
    return path


def _json_compact(value: object) -> str:
    import json

    if value in (None, ""):
        return ""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _col_letter(idx: int) -> str:
    letters = ""
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        letters = chr(65 + rem) + letters
    return letters
