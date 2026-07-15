"""JSON 응답을 정규화된 VehicleListing 으로 바꾸는 헬퍼.

캐피탈사 사이트 대부분은 그리드 데이터를 JSON(AJAX)으로 내려주지만, 응답의
모양(행 배열의 위치, 컬럼 키 이름)이 제각각이다. 그래서 실제 코드 수정 없이
설정(config)만으로 대응할 수 있도록:

    - resolve_path()  : "data.list[0].items" 같은 점 표기 경로로 값 추출
    - map_row()       : {정규화필드: [원본키 후보들]} 매핑으로 한 행을 변환
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from .models import VehicleListing

_INDEX_RE = re.compile(r"^(.*?)\[(\d+)\]$")


def resolve_path(data: Any, path: str) -> Any:
    """점 표기 경로로 중첩된 값을 꺼낸다.

    지원 형태: "a.b.c", "a.b[0].c", "list[2]".
    경로가 없으면 None 반환(예외를 던지지 않음 → 응답 구조가 흔들려도 견딤).
    빈 경로("")는 data 자체를 반환.
    """
    if not path:
        return data
    cur = data
    for token in path.split("."):
        token = token.strip()
        if not token:
            continue
        # 배열 인덱스 표기 처리: name[3]
        m = _INDEX_RE.match(token)
        idx = None
        if m:
            token, idx = m.group(1), int(m.group(2))
        if token:
            if isinstance(cur, Mapping) and token in cur:
                cur = cur[token]
            else:
                return None
        if idx is not None:
            if isinstance(cur, (list, tuple)) and -len(cur) <= idx < len(cur):
                cur = cur[idx]
            else:
                return None
    return cur


def _first_present(row: Mapping[str, Any], candidates: Iterable[str]) -> Any:
    """원본 키 후보들 중 값이 있는 첫 번째를 반환."""
    for key in candidates:
        val = resolve_path(row, key) if ("." in key or "[" in key) else row.get(key)
        if val not in (None, ""):
            return val
    return None


def _stringify(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return str(val).strip()


def map_row(
    row: Mapping[str, Any],
    source: str,
    field_map: Mapping[str, Any],
) -> VehicleListing:
    """원본 row 하나를 VehicleListing 으로 매핑.

    field_map 예시::

        {
            "model_name": ["carNm", "modelName"],   # 후보 여러 개 → 먼저 잡히는 값
            "vehicle_no": "carNo",                   # 단일 키도 허용
            "price": ["salePrc"],
        }

    매핑되지 않은 필드는 빈 문자열로 남고, 원본 row 전체는 raw 에 보존된다.
    """
    known = VehicleListing.known_fields()
    values: dict[str, Any] = {}
    for norm_field, spec in field_map.items():
        if norm_field not in known:
            # 알 수 없는 정규화 필드는 조용히 무시(오타 방지용으로 검증기에서 잡음)
            continue
        candidates = [spec] if isinstance(spec, str) else list(spec)
        values[norm_field] = _stringify(_first_present(row, candidates))

    values.setdefault("source", source)
    return VehicleListing(raw=dict(row), **values)


def rows_to_listings(
    payload: Any,
    source: str,
    rows_path: str,
    field_map: Mapping[str, Any],
) -> list[VehicleListing]:
    """JSON 응답 전체 → VehicleListing 목록."""
    rows = resolve_path(payload, rows_path)
    if rows is None:
        raise ValueError(
            f"[{source}] 응답에서 행 배열 경로 '{rows_path}' 를 찾지 못했습니다. "
            f"config 의 parse.rows_path 를 실제 응답 구조에 맞게 수정하세요."
        )
    if not isinstance(rows, list):
        raise ValueError(
            f"[{source}] rows_path '{rows_path}' 가 리스트가 아닙니다 "
            f"(실제 타입: {type(rows).__name__})."
        )
    return [map_row(r, source, field_map) for r in rows if isinstance(r, Mapping)]
