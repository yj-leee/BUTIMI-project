"""캐피탈사 어댑터 공통 인터페이스와 설정 기반 JSON 수집기.

각 캐피탈사마다 사이트 구조가 다르므로 어댑터로 분리한다. 다만 대부분의
캐피탈사가 'POST → JSON 그리드' 형태라, 코드를 새로 짜지 않고 설정(config)만
바꿔 대응할 수 있도록 JsonGridAdapter 를 공통 베이스로 제공한다.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import requests

from ..http_client import build_session
from ..models import VehicleListing
from ..parsing import resolve_path, rows_to_listings


class CapitalAdapter(ABC):
    """모든 캐피탈사 어댑터가 구현해야 하는 인터페이스."""

    #: 어댑터 등록 키 (예: "bnk"). 하위 클래스에서 반드시 지정.
    key: str = ""
    #: 사람이 읽는 이름 (예: "BNK캐피탈").
    display_name: str = ""

    @abstractmethod
    def fetch(self, max_items: int | None = None) -> list[VehicleListing]:
        """선구매 차량 매물 목록을 수집해 반환."""
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# 설정 스키마
# --------------------------------------------------------------------------- #
@dataclass
class PaginationSpec:
    """페이지네이션 방식.

    mode:
        - "none"   : 한 번의 요청으로 전부 받음
        - "page"   : 페이지 번호 증가 (page_param 에 1,2,3...)
        - "offset" : 시작 위치 증가 (page_param 에 0, size, 2*size...)
    """

    mode: str = "none"
    page_param: str = "page"       # 페이지 번호(또는 offset)를 담을 요청 파라미터명
    size_param: str = "pageSize"   # 페이지 크기를 담을 요청 파라미터명
    page_size: int = 20
    start_page: int = 1            # page 모드의 시작 번호 (0 또는 1)
    max_pages: int = 50            # 안전장치: 무한 루프 방지 상한
    total_path: str = ""           # 응답 내 전체 건수 경로(있으면 조기 종료에 사용)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any] | None) -> "PaginationSpec":
        d = d or {}
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class RequestConfig:
    """실제로 데이터를 내려주는 요청 명세.

    브라우저 개발자도구 Network 탭에서 캡처한 요청을 그대로 옮겨 담는 곳.
    """

    url: str = ""
    method: str = "POST"                       # "GET" | "POST"
    body_type: str = "form"                    # "form" | "json" | "query"
    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)   # GET 쿼리스트링
    body: dict[str, Any] = field(default_factory=dict)     # POST 바디(고정 파라미터)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "RequestConfig":
        kwargs = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        # params/body 안의 문서용 키(_로 시작)는 실제 전송에서 제외
        for key in ("params", "body"):
            if isinstance(kwargs.get(key), Mapping):
                kwargs[key] = {k: v for k, v in kwargs[key].items()
                               if not k.startswith("_")}
        return cls(**kwargs)


@dataclass
class ParseConfig:
    """응답 파싱 명세."""

    rows_path: str = ""                        # 행 배열 위치 (점 표기)
    field_map: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "ParseConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class AdapterConfig:
    """어댑터 하나의 전체 설정."""

    key: str
    display_name: str = ""
    request: RequestConfig = field(default_factory=RequestConfig)
    pagination: PaginationSpec = field(default_factory=PaginationSpec)
    parse: ParseConfig = field(default_factory=ParseConfig)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "AdapterConfig":
        return cls(
            key=d["key"],
            display_name=d.get("display_name", ""),
            request=RequestConfig.from_dict(d.get("request", {})),
            pagination=PaginationSpec.from_dict(d.get("pagination", {})),
            parse=ParseConfig.from_dict(d.get("parse", {})),
        )

    @classmethod
    def load(cls, path: str | Path) -> "AdapterConfig":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(raw)


# --------------------------------------------------------------------------- #
# 설정 기반 JSON 그리드 어댑터
# --------------------------------------------------------------------------- #
class JsonGridAdapter(CapitalAdapter):
    """'POST/GET → JSON 그리드' 형태를 설정만으로 처리하는 범용 어댑터.

    BNK 처럼 응답이 JSON 인 캐피탈사는 이 클래스를 그대로(혹은 얇게 상속해)
    쓰면 된다. HTML 표를 파싱해야 하는 사이트는 이 클래스를 상속해
    parse_response() 를 오버라이드한다.
    """

    def __init__(
        self,
        config: AdapterConfig,
        session: requests.Session | None = None,
    ) -> None:
        self.config = config
        self.key = config.key
        self.display_name = config.display_name or config.key
        self._session = session or build_session(config.request.headers)

    # -- 공개 API ---------------------------------------------------------- #
    def fetch(self, max_items: int | None = None) -> list[VehicleListing]:
        req = self.config.request
        if not req.url:
            raise ValueError(
                f"[{self.key}] request.url 이 비어 있습니다. "
                f"config/{self.key}.json 에 실제 API URL 을 넣으세요."
            )

        collected: list[VehicleListing] = []
        for page in self._iter_pages():
            payload = self._request_page(page)
            listings = self.parse_response(payload)
            if not listings:
                break
            collected.extend(listings)
            if max_items is not None and len(collected) >= max_items:
                collected = collected[:max_items]
                break
            if self._reached_total(payload, len(collected)):
                break
            if self.config.pagination.mode == "none":
                break
        return collected

    # -- 하위 클래스에서 커스터마이즈할 지점 ------------------------------- #
    def parse_response(self, payload: Any) -> list[VehicleListing]:
        """JSON 응답 → VehicleListing 목록. HTML 사이트면 오버라이드."""
        return rows_to_listings(
            payload,
            source=self.key,
            rows_path=self.config.parse.rows_path,
            field_map=self.config.parse.field_map,
        )

    def build_page_params(self, page_value: int) -> dict[str, Any]:
        """이번 페이지 요청에 얹을 페이지네이션 파라미터."""
        pg = self.config.pagination
        if pg.mode == "none":
            return {}
        params: dict[str, Any] = {pg.page_param: page_value}
        if pg.size_param:
            params[pg.size_param] = pg.page_size
        return params

    # -- 내부 구현 --------------------------------------------------------- #
    def _iter_pages(self):
        pg = self.config.pagination
        if pg.mode == "none":
            yield 0
            return
        step = pg.page_size if pg.mode == "offset" else 1
        value = pg.start_page
        for _ in range(pg.max_pages):
            yield value
            value += step

    def _request_page(self, page_value: int) -> Any:
        req = self.config.request
        page_params = self.build_page_params(page_value)

        query = dict(req.params)
        body = dict(req.body)
        if req.body_type == "query" or req.method.upper() == "GET":
            query.update(page_params)
        else:
            body.update(page_params)

        kwargs: dict[str, Any] = {"params": query} if query else {}
        if req.method.upper() == "POST":
            if req.body_type == "json":
                kwargs["json"] = body
            else:  # form
                kwargs["data"] = body

        resp = self._session.request(req.method.upper(), req.url, **kwargs)
        resp.raise_for_status()
        return self._decode(resp)

    @staticmethod
    def _decode(resp: requests.Response) -> Any:
        try:
            return resp.json()
        except ValueError as exc:
            snippet = resp.text[:300].replace("\n", " ")
            raise ValueError(
                "응답이 JSON 이 아닙니다. HTML 표를 반환하는 사이트라면 "
                "parse_response() 를 오버라이드하세요. 응답 앞부분: " + snippet
            ) from exc

    def _reached_total(self, payload: Any, got: int) -> bool:
        total_path = self.config.pagination.total_path
        if not total_path:
            return False
        total = resolve_path(payload, total_path)
        try:
            return total is not None and got >= int(total)
        except (TypeError, ValueError):
            return False
