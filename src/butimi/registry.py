"""캐피탈사 어댑터 레지스트리.

새 캐피탈사를 추가하려면:
    1. config/<key>.json 에 요청/파싱 설정을 만들고
    2. 필요하면 adapters/<key>.py 에 전용 어댑터를 두거나(HTML 파싱 등)
    3. 아래 register() 로 등록한다.

BNK 처럼 JSON 그리드라면 전용 클래스 없이 config 만으로 CONFIG_ONLY 에 올려도 된다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .adapters.base import AdapterConfig, CapitalAdapter, JsonGridAdapter
from .adapters.bnk import BNKAdapter

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"

# 전용 어댑터 클래스가 있는 캐피탈사
_FACTORIES: dict[str, Callable[[], CapitalAdapter]] = {
    "bnk": BNKAdapter,
}

# 전용 클래스 없이 config 만으로 구동하는 캐피탈사 키 목록 (JSON 그리드 전제)
_CONFIG_ONLY: set[str] = set()


def available() -> list[str]:
    """등록된 모든 캐피탈사 키."""
    return sorted(set(_FACTORIES) | _CONFIG_ONLY)


def register(key: str, factory: Callable[[], CapitalAdapter]) -> None:
    _FACTORIES[key] = factory


def get_adapter(key: str) -> CapitalAdapter:
    key = key.lower()
    if key in _FACTORIES:
        return _FACTORIES[key]()
    if key in _CONFIG_ONLY:
        config = AdapterConfig.load(CONFIG_DIR / f"{key}.json")
        return JsonGridAdapter(config)
    raise KeyError(
        f"알 수 없는 캐피탈사 '{key}'. 사용 가능: {', '.join(available()) or '(없음)'}"
    )
