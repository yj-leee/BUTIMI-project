"""커맨드라인 진입점.

사용 예::

    python -m butimi list                       # 지원 캐피탈사 목록
    python -m butimi fetch bnk                   # BNK 수집 → output/bnk_YYYYMMDD.csv
    python -m butimi fetch bnk --format xlsx     # 엑셀로
    python -m butimi fetch bnk --max 50 --out output/bnk.csv
    python -m butimi fetch all                   # 등록된 모든 캐피탈사
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from . import registry
from .exporters import to_csv, to_xlsx
from .models import VehicleListing

DEFAULT_OUT_DIR = Path("output")


def _default_out(key: str, fmt: str) -> Path:
    return DEFAULT_OUT_DIR / f"{key}_{date.today():%Y%m%d}.{fmt}"


def _export(listings, path: Path, fmt: str, include_raw: bool) -> None:
    if fmt == "csv":
        to_csv(listings, path, include_raw=include_raw)
    else:
        to_xlsx(listings, path, include_raw=include_raw)


def cmd_list(_: argparse.Namespace) -> int:
    keys = registry.available()
    if not keys:
        print("등록된 캐피탈사가 없습니다.")
        return 0
    print("지원 캐피탈사:")
    for key in keys:
        try:
            name = registry.get_adapter(key).display_name
        except Exception:  # 설정 누락 등 - 목록 표시는 계속
            name = "(설정 필요)"
        print(f"  - {key:8s} {name}")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    keys = registry.available() if args.key == "all" else [args.key]
    if args.key != "all" and args.key not in registry.available():
        print(f"알 수 없는 캐피탈사 '{args.key}'. 사용 가능: {', '.join(registry.available())}",
              file=sys.stderr)
        return 2

    exit_code = 0
    for key in keys:
        try:
            adapter = registry.get_adapter(key)
            listings = adapter.fetch(max_items=args.max)
        except Exception as exc:  # 한 곳이 실패해도 나머지는 계속
            print(f"[{key}] 수집 실패: {exc}", file=sys.stderr)
            exit_code = 1
            continue

        if not listings:
            print(f"[{key}] 수집된 매물이 없습니다.")
            continue

        out = Path(args.out) if (args.out and args.key != "all") else _default_out(key, args.format)
        _export(listings, out, args.format, args.include_raw)
        print(f"[{key}] {len(listings)}건 → {out}")
    return exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="butimi",
        description="캐피탈사 선구매 차량 리스트 수집기",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="지원 캐피탈사 목록")
    p_list.set_defaults(func=cmd_list)

    p_fetch = sub.add_parser("fetch", help="차량 리스트 수집 후 파일로 저장")
    p_fetch.add_argument("key", help="캐피탈사 키 (예: bnk) 또는 all")
    p_fetch.add_argument("--format", choices=("csv", "xlsx"), default="csv",
                         help="출력 형식 (기본: csv)")
    p_fetch.add_argument("--out", help="출력 파일 경로 (단일 캐피탈사일 때만)")
    p_fetch.add_argument("--max", type=int, default=None,
                         help="최대 수집 건수 (테스트용)")
    p_fetch.add_argument("--include-raw", action="store_true",
                         help="원본 응답(raw) 컬럼도 포함")
    p_fetch.set_defaults(func=cmd_fetch)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
