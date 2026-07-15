"""어댑터 수집 파이프라인 + 내보내기 테스트 (가짜 세션으로 네트워크 대체)."""

import csv
import json
from pathlib import Path

import pytest

from butimi.adapters.base import AdapterConfig, JsonGridAdapter
from butimi.exporters import to_csv, to_xlsx
from butimi.models import VehicleListing

FIXTURE = Path(__file__).parent / "fixtures" / "bnk_sample.json"

BNK_TEST_CONFIG = {
    "key": "bnk",
    "display_name": "BNK캐피탈",
    "request": {"url": "https://example.test/grid", "method": "POST", "body_type": "form"},
    "pagination": {"mode": "page", "page_param": "pageNo", "page_size": 20, "start_page": 1},
    "parse": {
        "rows_path": "data.list",
        "field_map": {
            "listing_id": ["seq"], "vehicle_no": ["carNo"], "model_name": ["carNm"],
            "year": ["yearType"], "mileage_km": ["distance"], "price": ["salePrice"],
            "region": ["regionNm"], "status": ["statusNm"],
        },
    },
}


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeSession:
    """첫 페이지엔 데이터, 이후 페이지엔 빈 리스트를 돌려주는 세션."""

    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        page = kwargs.get("data", {}).get("pageNo", 1)
        if page == 1:
            return _FakeResponse(self._payload)
        return _FakeResponse({"data": {"list": []}})


@pytest.fixture
def payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _adapter(payload):
    config = AdapterConfig.from_dict(BNK_TEST_CONFIG)
    return JsonGridAdapter(config, session=_FakeSession(payload)), config


def test_fetch_collects_and_stops_on_empty_page(payload):
    adapter, _ = _adapter(payload)
    listings = adapter.fetch()
    assert len(listings) == 2
    assert listings[0].model_name.startswith("그랜저")
    # 첫 페이지 데이터 + 두 번째 빈 페이지 = 최소 2회 요청
    assert len(adapter._session.calls) >= 2


def test_fetch_respects_max_items(payload):
    adapter, _ = _adapter(payload)
    listings = adapter.fetch(max_items=1)
    assert len(listings) == 1


def test_missing_url_raises():
    config = AdapterConfig.from_dict({"key": "x", "request": {"url": ""}})
    adapter = JsonGridAdapter(config, session=_FakeSession({}))
    with pytest.raises(ValueError):
        adapter.fetch()


def test_to_csv_roundtrip(tmp_path, payload):
    adapter, _ = _adapter(payload)
    listings = adapter.fetch()
    out = tmp_path / "bnk.csv"
    to_csv(listings, out)
    assert out.exists()

    with out.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 2
    assert rows[0]["model_name"].startswith("그랜저")
    assert rows[0]["source"] == "bnk"
    # 기본 내보내기엔 raw 컬럼이 없어야 함
    assert "raw" not in rows[0]


def test_to_csv_include_raw(tmp_path, payload):
    adapter, _ = _adapter(payload)
    listings = adapter.fetch()
    out = tmp_path / "bnk_raw.csv"
    to_csv(listings, out, include_raw=True)
    with out.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert "raw" in rows[0] and rows[0]["raw"]


def test_to_xlsx_smoke(tmp_path, payload):
    openpyxl = pytest.importorskip("openpyxl")
    adapter, _ = _adapter(payload)
    listings = adapter.fetch()
    out = tmp_path / "bnk.xlsx"
    to_xlsx(listings, out)
    assert out.exists()

    wb = openpyxl.load_workbook(out)
    ws = wb.active
    assert ws.max_row == 3  # 헤더 + 2건
    header = [c.value for c in ws[1]]
    assert "model_name" in header
