#!/usr/bin/env python3
"""한성자동차 전시장 판매사원(이름/연락처/전시장) 수집 → 엑셀 저장.

사용 (사이트 접근이 되는 PC 에서):
    PYTHONPATH=src python scripts/crawl_hansung_staff.py
    PYTHONPATH=src python scripts/crawl_hansung_staff.py --format csv
    PYTHONPATH=src python scripts/crawl_hansung_staff.py --save-html output/html

이미 저장해 둔 HTML 로 오프라인 재파싱 (전시장명은 파일명에서 유추/지정):
    PYTHONPATH=src python scripts/crawl_hansung_staff.py --from-html output/html
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from butimi import hansung_staff as hs  # noqa: E402


def _parse_saved_html(html_dir: Path) -> list[hs.StaffMember]:
    members: list[hs.StaffMember] = []
    list_file = html_dir / "retail-store.html"
    name_by_slug: dict[str, str] = {}
    if list_file.exists():
        for name, url in hs.discover_store_links(list_file.read_text(encoding="utf-8")):
            slug = url.rstrip("/").rsplit("/", 1)[-1]
            name_by_slug[slug] = name
    for path in sorted(html_dir.glob("retail-store-*.html")):
        slug = path.stem
        showroom = name_by_slug.get(slug, slug)
        members.extend(hs.parse_staff(path.read_text(encoding="utf-8"), showroom))
    return hs.dedupe(members)


def main() -> int:
    ap = argparse.ArgumentParser(description="한성자동차 전시장 판매사원 수집")
    ap.add_argument("--format", choices=["xlsx", "csv"], default="xlsx")
    ap.add_argument("--out", help="출력 파일 경로(미지정 시 output/ 아래 자동 생성)")
    ap.add_argument("--save-html", metavar="DIR", help="수집한 HTML 을 저장할 폴더")
    ap.add_argument("--from-html", metavar="DIR",
                    help="네트워크 대신 저장된 HTML 폴더에서 파싱")
    ap.add_argument("--delay", type=float, default=0.5, help="요청 간 지연(초)")
    args = ap.parse_args()

    if args.from_html:
        members = _parse_saved_html(Path(args.from_html))
    else:
        members = hs.crawl(save_html_dir=args.save_html, delay=args.delay)

    if not members:
        print("수집된 판매사원이 없습니다. 페이지 구조를 확인하세요(--save-html).",
              file=sys.stderr)
        return 1

    stamp = date.today().strftime("%Y%m%d")
    default = Path("output") / f"hansung_staff_{stamp}.{args.format}"
    out = Path(args.out) if args.out else default

    if args.format == "csv":
        saved = hs.to_csv(members, out)
    else:
        saved = hs.to_xlsx(members, out)

    stores = sorted({m.showroom for m in members})
    print(f"판매사원 {len(members)}명 · 전시장 {len(stores)}곳 → {saved}")

    missing = hs.missing_showrooms(members)
    if missing:
        print("\n[점검] 판매사원이 수집되지 않은(=확인 필요) 전시장:")
        for name in missing:
            print(f"  - {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
