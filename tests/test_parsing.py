"""파싱/매핑 로직 단위 테스트 (네트워크 불필요)."""

import json
from pathlib import Path

import pytest

from butimi.parsing import resolve_path, map_row, rows_to_listings

FIXTURE = Path(__file__).parent / "fixtures" / "bnk_sample.json"


@pytest.fixture
def payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_resolve_path_nested():
    data = {"a": {"b": [{"c": 42}]}}
    assert resolve_path(data, "a.b[0].c") == 42
    assert resolve_path(data, "a.b") == [{"c": 42}]
    assert resolve_path(data, "") == data


def test_resolve_path_missing_returns_none():
    data = {"a": {"b": 1}}
    assert resolve_path(data, "a.x.y") is None
    assert resolve_path(data, "a.b[5]") is None


def test_map_row_uses_first_present_candidate():
    row = {"modelName": "쏘나타", "carNm": ""}
    listing = map_row(row, "bnk", {"model_name": ["carNm", "modelName"]})
    # carNm 은 빈 값이라 modelName 이 채택되어야 함
    assert listing.model_name == "쏘나타"
    assert listing.source == "bnk"
    assert listing.raw == row


def test_map_row_preserves_raw_and_ignores_unknown_field():
    row = {"carNm": "K5", "junk": 1}
    listing = map_row(row, "bnk", {"model_name": "carNm", "not_a_field": "junk"})
    assert listing.model_name == "K5"
    assert listing.raw["junk"] == 1


FIELD_MAP = {
    "listing_id": ["seq"],
    "vehicle_no": ["carNo"],
    "model_name": ["carNm"],
    "trim": ["grade"],
    "year": ["yearType"],
    "first_reg_date": ["firstRegDt"],
    "mileage_km": ["distance"],
    "fuel": ["fuelNm"],
    "transmission": ["gearNm"],
    "color": ["colorNm"],
    "price": ["salePrice"],
    "region": ["regionNm"],
    "status": ["statusNm"],
    "posted_at": ["regDt"],
}


def test_rows_to_listings(payload):
    listings = rows_to_listings(payload, "bnk", "data.list", FIELD_MAP)
    assert len(listings) == 2
    first = listings[0]
    assert first.model_name == "그랜저 IG 2.4 프리미엄"
    assert first.vehicle_no == "12가3456"
    assert first.price == "16,900,000"
    assert first.region == "부산"
    assert first.listing_id == "A1001"


def test_rows_to_listings_bad_path_raises(payload):
    with pytest.raises(ValueError):
        rows_to_listings(payload, "bnk", "data.nope", FIELD_MAP)
