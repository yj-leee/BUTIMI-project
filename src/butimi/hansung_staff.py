"""한성자동차(메르세데스-벤츠) 전시장 판매사원 수집기.

대상: https://mb.hansung.co.kr/sales/retail-store
목표: 각 전시장 페이지에서 **판매사원 이름 / 연락처 / 소속 전시장** 을 추출해
      엑셀(.xlsx)로 저장한다.

동작 개요
---------
1. 목록 페이지(``/sales/retail-store``)에서 개별 전시장 페이지 링크
   (``/sales/retail-store-<n>``)와 전시장 이름을 찾는다.
2. 각 전시장 페이지 HTML 을 받아 판매사원 블록을 파싱한다.
3. ``이름 / 연락처 / 전시장`` 세 컬럼으로 정규화해 반환한다.

파싱은 **텍스트 기반 휴리스틱**이라 사이트 마크업이 바뀌어도 비교적 견고하다.
전화번호를 앵커로 잡고, 그 앞쪽에서 사람 이름처럼 보이는 토큰을 짝지운다.
구조가 예상과 다르면 ``parse_staff`` 의 규칙만 손보면 된다.

주의: 이 저장소를 만든 실행 환경은 네트워크 정책상 ``mb.hansung.co.kr`` 접근이
차단돼 있다. 그래서 실제 사이트로의 수집은 **사이트 접근이 되는 PC**에서 실행해야
한다(파싱 로직은 tests 로 검증됨). 오프라인 검증을 위해 ``--save-html`` 로 받은
HTML 을 저장해 두고 ``parse_staff`` 를 재실행할 수 있다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from html import unescape
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin

BASE_URL = "https://mb.hansung.co.kr/sales/retail-store"

# 사용자가 "아직 크롤링 안 됐다"고 알려준 전시장들. 수집 후 누락 점검용 기준 목록.
EXPECTED_SHOWROOMS: tuple[str, ...] = (
    "강남/청담 전시장", "삼성 전시장", "서초 전시장", "방배 전시장", "용산 전시장",
    "강남 자곡 전시장", "인천 송도 전시장", "분당 서현 전시장", "인천 전시장",
    "수원 전시장", "안성 전시장", "대전 전시장", "대전 유성 전시장",
    "원주 전시장", "성남 전시장",
)


def _norm_store(name: str) -> str:
    """전시장 이름 비교용 정규화(공백/구분자 제거)."""
    return re.sub(r"[\s/·]", "", name)


def missing_showrooms(members: Iterable["StaffMember"]) -> list[str]:
    """EXPECTED_SHOWROOMS 중 판매사원이 하나도 수집되지 않은 전시장 목록."""
    got = {_norm_store(m.showroom) for m in members}
    return [s for s in EXPECTED_SHOWROOMS if _norm_store(s) not in got]

# 전화번호: 010-1234-5678 / 02-123-4567 / 031-710-8000 / 02.3479.8600 등
_PHONE_RE = re.compile(r"0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}")

# 개별 전시장 페이지 링크: /sales/retail-store-12 형태
_STORE_LINK_RE = re.compile(
    r'href=["\'](?P<href>[^"\']*?/sales/retail-store-\d+)["\'][^>]*>(?P<text>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)

# 이름으로 오인하기 쉬운 직급/직책/일반 단어 — 이름 후보에서 제외한다.
_NAME_STOPWORDS = {
    "팀장", "부장", "차장", "과장", "대리", "사원", "이사", "상무", "전무",
    "실장", "본부장", "지점장", "센터장", "소장", "마스터", "마스터팀",
    "판매", "판매팀", "영업", "영업팀", "전시장", "컨설턴트", "매니저",
    "세일즈", "세일즈컨설턴트", "판매사원", "판매팀장", "선임", "책임",
    "메르세데스", "벤츠", "한성자동차", "고객센터", "대표전화", "문의",
    # 전화/연락처 라벨 — 이름으로 오인 방지
    "직통", "휴대폰", "휴대전화", "전화", "팩스", "사무실", "상담",
    "이메일", "메일", "예약", "시승", "카카오", "네이버",
}

# 사람 이름: 한글 2~4자. (성+이름)
_NAME_RE = re.compile(r"^[가-힣]{2,4}$")


@dataclass
class StaffMember:
    """전시장 판매사원 한 명."""

    name: str          # 이름
    contact: str       # 연락처(전화번호)
    showroom: str      # 소속 전시장
    detail_url: str = ""  # 출처 전시장 페이지 URL

    def to_row(self) -> dict[str, str]:
        return {"이름": self.name, "연락처": self.contact, "전시장": self.showroom}


# --------------------------------------------------------------------------- #
# HTML → 텍스트
# --------------------------------------------------------------------------- #

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b.*?</\1>", re.IGNORECASE | re.DOTALL)
# 블록 경계로 삼을 태그(줄바꿈으로 치환)
_BLOCK_BOUNDARY_RE = re.compile(
    r"</?(?:div|p|li|tr|td|th|br|h[1-6]|section|article|span|dt|dd|table|ul|ol)\b[^>]*>",
    re.IGNORECASE,
)


def html_to_lines(html: str) -> list[str]:
    """HTML 을 블록 단위 텍스트 줄 목록으로 변환."""
    text = _SCRIPT_STYLE_RE.sub("\n", html)
    text = _BLOCK_BOUNDARY_RE.sub("\n", text)
    text = _TAG_RE.sub("", text)
    text = unescape(text)
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in text.splitlines()]
    return [ln for ln in lines if ln]


def normalize_phone(raw: str) -> str:
    """전화번호를 하이픈 표기로 정규화. 실패하면 원문 반환."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11:  # 010-XXXX-XXXX
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    if len(digits) == 10:
        if digits.startswith("02"):  # 02-XXXX-XXXX
            return f"{digits[:2]}-{digits[2:6]}-{digits[6:]}"
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"  # 031-XXX-XXXX
    if len(digits) == 9 and digits.startswith("02"):  # 02-XXX-XXXX
        return f"{digits[:2]}-{digits[2:5]}-{digits[5:]}"
    return raw.strip()


def _looks_like_name(token: str) -> bool:
    token = token.strip()
    if not _NAME_RE.match(token):
        return False
    if token in _NAME_STOPWORDS:
        return False
    # '판매팀장' 처럼 직급 접미로 끝나는 4글자 토큰 제외
    if any(token.endswith(sfx) for sfx in ("팀장", "부장", "과장", "대리", "이사", "실장")):
        return False
    return True


# --------------------------------------------------------------------------- #
# 파싱
# --------------------------------------------------------------------------- #

def parse_staff(html: str, showroom: str, detail_url: str = "") -> list[StaffMember]:
    """전시장 페이지 HTML 에서 (이름, 연락처, 전시장) 목록을 추출한다.

    전략: 텍스트 줄 목록을 훑으며 전화번호를 만나면, 직전에 등장한
    '이름처럼 보이는 줄'과 짝짓는다. 한 사원 블록에 전화가 여러 개(휴대폰+직통)면
    첫 번째만 사용하고, 같은 이름의 연속 중복은 제거한다.
    """
    lines = html_to_lines(html)
    members: list[StaffMember] = []
    pending_name: str | None = None
    last_key: tuple[str, str] | None = None

    for line in lines:
        # 한 줄 안에 이름 토큰이 단독으로 있으면 후보로 기억
        if _looks_like_name(line):
            pending_name = line

        phones = _PHONE_RE.findall(line)
        if not phones:
            continue

        contact = normalize_phone(phones[0])

        # 이름이 같은 줄 안에 섞여 있을 수도 있으니 줄에서도 이름 토큰을 탐색
        name = pending_name
        if name is None:
            for tok in re.split(r"[\s/|·,]+", _PHONE_RE.sub(" ", line)):
                if _looks_like_name(tok):
                    name = tok
                    break
        if not name:
            continue

        key = (name, contact)
        if key == last_key:
            continue
        members.append(StaffMember(name=name, contact=contact,
                                   showroom=showroom, detail_url=detail_url))
        last_key = key
        pending_name = None

    return members


def discover_store_links(list_html: str, base_url: str = BASE_URL) -> list[tuple[str, str]]:
    """목록 페이지 HTML 에서 (전시장 이름, 절대 URL) 목록을 추출(중복 제거)."""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for m in _STORE_LINK_RE.finditer(list_html):
        url = urljoin(base_url, m.group("href"))
        name = unescape(_TAG_RE.sub("", m.group("text"))).strip()
        name = re.sub(r"\s+", " ", name)
        if url in seen:
            continue
        seen.add(url)
        found.append((name, url))
    return found


# --------------------------------------------------------------------------- #
# 수집 (네트워크)
# --------------------------------------------------------------------------- #

def crawl(
    base_url: str = BASE_URL,
    *,
    session=None,
    save_html_dir: str | Path | None = None,
    delay: float = 0.5,
) -> list[StaffMember]:
    """실제 사이트를 돌며 모든 전시장의 판매사원을 수집한다.

    사이트 접근이 가능한 환경에서 실행할 것. ``save_html_dir`` 을 주면 받은
    HTML 을 함께 저장해 오프라인 재파싱에 쓸 수 있다.
    """
    import time

    if session is None:
        from .http_client import build_session
        session = build_session(extra_headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": base_url,
        })

    save_dir = Path(save_html_dir) if save_html_dir else None
    if save_dir:
        save_dir.mkdir(parents=True, exist_ok=True)

    list_html = session.get(base_url).text
    if save_dir:
        (save_dir / "retail-store.html").write_text(list_html, encoding="utf-8")

    stores = discover_store_links(list_html, base_url)
    if not stores:
        raise RuntimeError(
            "목록 페이지에서 전시장 링크를 찾지 못했습니다. 페이지가 JS 로 렌더링되거나 "
            "마크업이 바뀌었을 수 있습니다. --save-html 로 HTML 을 확인해 셀렉터를 조정하세요."
        )

    all_members: list[StaffMember] = []
    for name, url in stores:
        html = session.get(url).text
        if save_dir:
            slug = url.rstrip("/").rsplit("/", 1)[-1] or "store"
            (save_dir / f"{slug}.html").write_text(html, encoding="utf-8")
        all_members.extend(parse_staff(html, showroom=name, detail_url=url))
        if delay:
            time.sleep(delay)

    return dedupe(all_members)


def dedupe(members: Iterable[StaffMember]) -> list[StaffMember]:
    """(이름, 연락처, 전시장) 기준 중복 제거, 순서 보존."""
    out: list[StaffMember] = []
    seen: set[tuple[str, str, str]] = set()
    for m in members:
        key = (m.name, m.contact, m.showroom)
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    return out


# --------------------------------------------------------------------------- #
# 엑셀 내보내기
# --------------------------------------------------------------------------- #

COLUMNS = ["이름", "연락처", "전시장"]


def to_xlsx(members: Iterable[StaffMember], path: str | Path,
            sheet_name: str = "판매사원") -> Path:
    try:
        from openpyxl import Workbook
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "엑셀(.xlsx) 저장에는 openpyxl 이 필요합니다. `pip install openpyxl`."
        ) from exc

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31]
    ws.append(COLUMNS)
    for m in members:
        row = m.to_row()
        ws.append([row[c] for c in COLUMNS])

    ws.freeze_panes = "A2"
    widths = {"이름": 14, "연락처": 20, "전시장": 24}
    for idx, col in enumerate(COLUMNS, start=1):
        ws.column_dimensions[chr(64 + idx)].width = widths.get(col, 16)

    wb.save(path)
    return path


def to_csv(members: Iterable[StaffMember], path: str | Path) -> Path:
    import csv

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for m in members:
            writer.writerow(m.to_row())
    return path


def _member_dicts(members: Iterable[StaffMember]) -> list[dict]:
    return [asdict(m) for m in members]
