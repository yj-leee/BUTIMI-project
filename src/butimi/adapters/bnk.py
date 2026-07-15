"""BNK캐피탈 선구매 차량 리스트 어댑터.

대상 페이지: https://web.bnkcapital.co.kr/view/prtn/alem/PrtnAlem540M01

BNK 를 포함한 대부분의 캐피탈사 그리드는 'POST → JSON' 형태라, 별도 로직 없이
JsonGridAdapter 를 설정(config/bnk.json)으로 구동한다. 만약 BNK 응답이 HTML
표라면 아래 parse_response() 를 오버라이드하면 된다(주석 참고).

  ⚠️ 실제 요청 URL/파라미터/응답 구조는 사이트 접근이 가능한 환경에서
      브라우저 개발자도구 → Network 탭으로 캡처해 config/bnk.json 에 채워야 한다.
      (README 의 "실제 사이트 연결" 절 참고)
"""

from __future__ import annotations

from pathlib import Path

import requests

from .base import AdapterConfig, JsonGridAdapter

# 프로젝트 루트 기준 기본 설정 파일 경로
_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "bnk.json"


class BNKAdapter(JsonGridAdapter):
    key = "bnk"
    display_name = "BNK캐피탈"

    def __init__(
        self,
        config: AdapterConfig | None = None,
        config_path: str | Path | None = None,
        session: requests.Session | None = None,
    ) -> None:
        if config is None:
            path = Path(config_path) if config_path else _CONFIG_PATH
            config = AdapterConfig.load(path)
        super().__init__(config, session=session)

    # ------------------------------------------------------------------ #
    # BNK 응답이 JSON 이 아니라 HTML 표라면 아래 주석을 해제해 오버라이드한다.
    # (예시 골격 — 실제 셀렉터는 페이지 구조에 맞게 수정)
    # ------------------------------------------------------------------ #
    # def parse_response(self, payload):
    #     from bs4 import BeautifulSoup
    #     from ..models import VehicleListing
    #     html = payload if isinstance(payload, str) else ""
    #     soup = BeautifulSoup(html, "html.parser")
    #     listings = []
    #     for tr in soup.select("table.list tbody tr"):
    #         tds = [td.get_text(strip=True) for td in tr.select("td")]
    #         if not tds:
    #             continue
    #         listings.append(VehicleListing(
    #             source=self.key,
    #             model_name=tds[1],
    #             year=tds[2],
    #             mileage_km=tds[3],
    #             price=tds[4],
    #             raw={"cells": tds},
    #         ))
    #     return listings
