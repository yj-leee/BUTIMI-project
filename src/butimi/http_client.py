"""재시도가 붙은 requests 세션 래퍼."""

from __future__ import annotations

from typing import Any, Mapping

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}


def build_session(
    extra_headers: Mapping[str, str] | None = None,
    total_retries: int = 3,
    backoff_factor: float = 1.0,
    timeout: float = 20.0,
) -> requests.Session:
    """네트워크 오류/5xx 에 지수 백오프로 재시도하는 세션 생성."""
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    if extra_headers:
        session.headers.update(extra_headers)

    retry = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    # 세션 기본 타임아웃을 request 래퍼로 강제
    session.request = _with_timeout(session.request, timeout)  # type: ignore[method-assign]
    return session


def _with_timeout(func: Any, timeout: float) -> Any:
    def wrapper(method: str, url: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", timeout)
        return func(method, url, **kwargs)

    return wrapper
