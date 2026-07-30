#!/usr/bin/env python3
"""한성자동차 세일즈 컨설턴트(이름/연락처/전시장/팀) 수집 → 엑셀 저장.

실제 사이트는 2단계 구조다:
  - 목록 페이지  /sales/consultant-<n>       : 전시장별 컨설턴트 이름/직급/팀
  - 상세 페이지  /sales/consultant-view-<id> : 개인 연락처(휴대폰)
이 스크립트는 목록에서 상세 링크를 모아 각 상세 페이지를 자동 방문해 연락처까지
채운다(= 사람마다 일일이 클릭할 필요 없음).

사용 (사이트 접근이 되는 PC 에서):
    Windows: set PYTHONPATH=src && python scripts\\crawl_hansung_staff.py
    macOS  : PYTHONPATH=src python scripts/crawl_hansung_staff.py
    옵션   : --format csv | --save-html output\\html | --from-html output\\html
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from butimi import hansung_staff as hs  # noqa: E402


def _parse_saved_html(html_dir: Path) -> list[hs.StaffMember]:
    """저장해 둔 HTML 폴더에서 오프라인 파싱. 상세 페이지 파일 우선 사용."""
    members: list[hs.StaffMember] = []
    view_files = sorted(html_dir.glob("consultant-view-*.html"))
    for path in view_files:
        m = hs.parse_detail(path.read_text(encoding="utf-8"), detail_url=path.stem)
        if m:
            members.append(m)
    if not members:  # 상세 파일이 없으면 목록 텍스트에서라도 이름/전시장 추출
        for path in sorted(html_dir.glob("*.html")):
            members.extend(hs.parse_staff(path.read_text(encoding="utf-8"), showroom=""))
    return hs.dedupe(members)


def main() -> int:
    ap = argparse.ArgumentParser(description="한성자동차 세일즈 컨설턴트 수집")
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
        members = hs.crawl_consultants(save_html_dir=args.save_html, delay=args.delay)

    if not members:
        print("수집된 컨설턴트가 없습니다. 페이지가 JS 로 렌더링될 수 있습니다."
              " --save-html 로 HTML 을 저장해 확인하세요.", file=sys.stderr)
        return 1

    stamp = date.today().strftime("%Y%m%d")
    default = Path("output") / f"hansung_staff_{stamp}.{args.format}"
    out = Path(args.out) if args.out else default

    if args.format == "csv":
        saved = hs.to_csv(members, out)
    else:
        saved = hs.to_xlsx(members, out)

    stores = sorted({m.showroom for m in members if m.showroom})
    no_phone = sum(1 for m in members if not m.contact)
    print(f"컨설턴트 {len(members)}명 · 전시장 {len(stores)}곳 → {saved}")
    if no_phone:
        print(f"  · 연락처 미확보 {no_phone}명(상세 페이지에서 번호를 못 찾음)")

    missing = hs.missing_showrooms(members)
    if missing:
        print("\n[점검] 컨설턴트가 수집되지 않은(=확인 필요) 전시장:")
        for name in missing:
            print(f"  - {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
