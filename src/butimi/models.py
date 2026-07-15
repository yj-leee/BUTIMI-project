"""캐피탈사 간 공통으로 쓰는 정규화된 차량 매물 스키마."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, asdict
from datetime import datetime, timezone
from typing import Any, ClassVar


@dataclass
class VehicleListing:
    """캐피탈사 선구매 차량 한 건.

    사이트마다 제공하는 컬럼이 조금씩 다르므로, 자주 쓰는 필드만 정규화하고
    나머지 원본 값은 전부 ``raw`` 에 보존한다. 매핑되지 않은 값 때문에
    데이터가 유실되지 않도록 하기 위함.
    """

    source: str                      # 캐피탈사 키 (예: "bnk")
    listing_id: str = ""             # 사이트 내 매물 고유 id (없으면 차량번호 등으로 대체)
    vehicle_no: str = ""             # 차량번호 (예: 12가3456)
    model_name: str = ""             # 차명 / 모델
    trim: str = ""                   # 세부모델 / 등급
    year: str = ""                   # 연식
    first_reg_date: str = ""         # 최초등록일
    mileage_km: str = ""             # 주행거리(km)
    fuel: str = ""                   # 연료
    transmission: str = ""           # 변속기
    color: str = ""                  # 색상
    price: str = ""                  # 가격 / 매입가 (원본 문자열 그대로 보존)
    region: str = ""                 # 지역
    status: str = ""                 # 상태 (판매중 등)
    posted_at: str = ""              # 게시/등록일
    detail_url: str = ""             # 상세 페이지 URL
    fetched_at: str = field(         # 수집 시각 (UTC ISO8601)
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    raw: dict[str, Any] = field(default_factory=dict)  # 사이트 원본 row 전체

    # CSV/엑셀에 노출할 컬럼 순서 (raw 제외). 표의 열 순서를 여기서 통제한다.
    EXPORT_FIELDS: ClassVar[tuple[str, ...]] = (
        "source", "listing_id", "vehicle_no", "model_name", "trim",
        "year", "first_reg_date", "mileage_km", "fuel", "transmission",
        "color", "price", "region", "status", "posted_at",
        "detail_url", "fetched_at",
    )

    def to_row(self, include_raw: bool = False) -> dict[str, Any]:
        """표 한 행으로 직렬화. raw 는 옵션."""
        row = {name: getattr(self, name) for name in self.EXPORT_FIELDS}
        if include_raw:
            row["raw"] = self.raw
        return row

    @classmethod
    def export_columns(cls, include_raw: bool = False) -> list[str]:
        cols = list(cls.EXPORT_FIELDS)
        if include_raw:
            cols.append("raw")
        return cols

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def known_fields(cls) -> set[str]:
        return {f.name for f in fields(cls)} - {"raw", "EXPORT_FIELDS"}
