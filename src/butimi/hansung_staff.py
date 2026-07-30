"""한성자동차(메르세데스-벤츠) 세일즈 컨설턴트(판매사원) 수집기.

대상: https://mb.hansung.co.kr/sales/consultant-1 (전시장별 세일즈 컨설턴트)
목표: **이름 / 연락처 / 전시장 / 팀** 을 추출해 엑셀(.xlsx)로 저장한다.

사이트 구조(2단계)
------------------
- 목록 페이지  ``/sales/consultant-<n>``       : 전시장별 컨설턴트 이름/직급/팀
  (전화번호는 여기 없음)
- 상세 페이지  ``/sales/consultant-view-<id>`` : 개인 연락처(휴대폰)가 여기 있음

그래서 ``crawl_consultants`` 는 목록/지역 페이지를 훑어 ``consultant-view`` 링크를
모두 모은 뒤, 각 상세 페이지를 방문해 이름·연락처·전시장·팀을 뽑는다. 사람마다
손으로 클릭할 필요가 없다.

주의
----
- 이 저장소를 만든 실행 환경은 네트워크 정책상 ``mb.hansung.co.kr`` 접근이 **차단**
  돼 있다. 실제 수집은 **사이트 접근이 되는 PC**에서 실행할 것(파싱 로직은 tests
  로 검증됨).
- 목록이 JS 로 렌더링되어 링크가 안 잡히면 ``--save-html`` 로 HTML 을 저장해
  구조를 확인하거나 Playwright(browser) 방식으로 확장한다.
- 상세 페이지의 실제 HTML 은 아직 확인하지 못해, ``parse_detail`` 은 전화/이름/
  전시장을 방어적으로 추출한다. 필드가 비면 저장한 상세 HTML 로 규칙을 맞추면 된다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from html import unescape
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin

BASE_URL = "https://mb.hansung.co.kr/sales/retail-store"

# 세일즈 컨설턴트(판매사원) 실제 구조:
#   - 목록 페이지  /sales/consultant-<n>            → 전시장별 컨설턴트 이름/직급/팀 (전화 없음)
#   - 상세 페이지  /sales/consultant-view-<id>      → 개인 연락처(휴대폰)가 여기 있음
#   - 지역 탭      /sales/consultant-7,10,49 ...    → 서울/경인/그 외 지역 목록
# 개인 연락처는 상세 페이지에 있으므로, 목록에서 상세 링크를 모아 하나씩 방문한다.
SALES_HOST = "https://mb.hansung.co.kr"

# 스파이더 시작점(목록/지역 페이지). 여기서 consultant-view 링크들을 긁어 모은다.
SEED_LISTING_URLS: tuple[str, ...] = (
    "https://mb.hansung.co.kr/sales/consultant-1",   # 강남/청담
    "https://mb.hansung.co.kr/sales/consultant-3",   # 삼성
    "https://mb.hansung.co.kr/sales/consultant-4",   # 서초
    "https://mb.hansung.co.kr/sales/consultant-5",   # 방배
    "https://mb.hansung.co.kr/sales/consultant-6",   # 용산
    "https://mb.hansung.co.kr/sales/consultant-7",   # 강남 자곡 / 서울 지역
    "https://mb.hansung.co.kr/sales/consultant-10",  # 경인 지역
    "https://mb.hansung.co.kr/sales/consultant-49",  # 그 외 지역
)

# 전시장별 팀 범위(사용자 제공). 페이지에서 개인 팀이 안 잡히면 이 값으로 채운다.
# 수집 후 누락 점검(EXPECTED_SHOWROOMS)의 기준 목록이기도 하다.
SHOWROOM_TEAM_RANGE: dict[str, str] = {
    "강남/청담 전시장": "2팀~9팀",
    "삼성 전시장": "2팀~5팀",
    "서초 전시장": "2팀~마스터팀",
    "방배 전시장": "2팀~마스터팀",
    "용산 전시장": "2팀~마스터팀",
    "강남 자곡 전시장": "2팀~3팀",
    "인천 송도 전시장": "2팀~3팀",
    "분당 서현 전시장": "2팀~4팀",
    "인천 전시장": "2팀~3팀",
    "수원 전시장": "2팀~4팀",
    "안성 전시장": "2팀~마스터팀",
    "대전 전시장": "2팀~마스터팀",
    "대전 유성 전시장": "2팀~3팀",
    "원주 전시장": "2팀",
    "성남 전시장": "2팀",
}

EXPECTED_SHOWROOMS: tuple[str, ...] = tuple(SHOWROOM_TEAM_RANGE)

# 개인 소속 팀 토큰: "3팀", "판매 5팀", "마스터팀" 등
_TEAM_RE = re.compile(r"(?:마스터팀|\d+\s*팀)")


def team_range_for(showroom: str) -> str:
    """전시장 이름으로 팀 범위를 찾는다(공백/구분자 무시 매칭). 없으면 빈 문자열."""
    target = _norm_store(showroom)
    for name, rng in SHOWROOM_TEAM_RANGE.items():
        if _norm_store(name) == target:
            return rng
    return ""


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
    team: str = ""     # 팀(개인 소속 팀 또는 전시장 팀 범위)
    detail_url: str = ""  # 출처 전시장 페이지 URL

    def to_row(self) -> dict[str, str]:
        return {
            "이름": self.name,
            "연락처": self.contact,
            "전시장": self.showroom,
            "팀": self.team,
        }


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
    pending_team: str = ""
    fallback_team = team_range_for(showroom)
    last_key: tuple[str, str] | None = None

    for line in lines:
        # 한 줄 안에 이름 토큰이 단독으로 있으면 후보로 기억
        if _looks_like_name(line):
            pending_name = line

        # 개인 팀 토큰("3팀", "마스터팀")이 보이면 기억
        team_hit = _TEAM_RE.search(line)
        if team_hit:
            pending_team = re.sub(r"\s+", "", team_hit.group())

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
        members.append(StaffMember(
            name=name, contact=contact, showroom=showroom,
            team=pending_team or fallback_team, detail_url=detail_url,
        ))
        last_key = key
        pending_name = None
        pending_team = ""

    return members


# --------------------------------------------------------------------------- #
# 세일즈 컨설턴트(2단계: 목록 → 상세) 구조 파싱
# --------------------------------------------------------------------------- #

# 개인 상세 페이지 링크: /sales/consultant-view-1450
_VIEW_LINK_RE = re.compile(r'/sales/consultant-view-\d+', re.IGNORECASE)
# 목록/지역/해시태그 링크(스파이더가 더 따라갈 후보)
_LISTING_LINK_RE = re.compile(
    r'/sales/consultant(?:-hashtag/\d+|-\d+)(?![\w-])', re.IGNORECASE)

# 직급어(상세 페이지에서 이름 옆 직급 추출용)
_RANK_WORDS = ("팀장", "이사", "상무", "전무", "본부장", "지점장", "센터장",
               "부장", "차장", "과장", "대리", "선임", "책임", "매니저", "사원")
_RANK_RE = re.compile("(?:" + "|".join(_RANK_WORDS) + ")")


def discover_consultant_view_links(html: str, base_url: str = SALES_HOST) -> list[str]:
    """HTML 안의 모든 개인 상세 페이지(consultant-view) 절대 URL을 중복 없이 반환."""
    seen: set[str] = set()
    out: list[str] = []
    for m in _VIEW_LINK_RE.finditer(html):
        url = urljoin(base_url, m.group(0))
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _discover_listing_links(html: str, base_url: str = SALES_HOST) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in _LISTING_LINK_RE.finditer(html):
        url = urljoin(base_url, m.group(0))
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


# 알려진 전시장 이름(팀 범위 목록 + 페이지에서 확인된 추가 전시장). 긴 이름 우선.
KNOWN_SHOWROOMS: tuple[str, ...] = tuple(sorted(
    set(SHOWROOM_TEAM_RANGE) | {"수원 권선 전시장", "춘천 전시장", "강릉 전시장"},
    key=lambda s: len(_norm_store(s)), reverse=True,
))


def _find_showroom(text: str) -> str:
    """텍스트에서 전시장 이름을 찾는다. 알려진 이름을 우선 매칭(더 구체적인 것 먼저)."""
    norm = _norm_store(text)
    for name in KNOWN_SHOWROOMS:
        if _norm_store(name) in norm:
            return name
    # 폴백: 'OO 전시장' 패턴(앞 단어 최대 2개까지만)
    m = re.search(r"[가-힣]{2,4}(?:\s[가-힣]{2,4}){0,2}\s*전시장", text)
    return re.sub(r"\s+", " ", m.group()).strip() if m else ""


def parse_detail(html: str, detail_url: str = "") -> StaffMember | None:
    """개인 상세 페이지(consultant-view)에서 이름/연락처/전시장/팀을 추출.

    실제 상세 페이지 HTML 을 아직 확인하지 못해, 이름은 <title>/og:title/헤딩에서,
    연락처는 휴대폰(010) 우선으로, 전시장은 'OO 전시장' 패턴으로 뽑는 방어적 구현.
    필드가 비면 --save-html 로 실제 페이지를 저장해 규칙을 맞추면 된다.
    """
    lines = html_to_lines(html)
    text = "\n".join(lines)

    # 이름: og:title / <title> 우선(예: "전석영 | 한성자동차"), 없으면 첫 이름 토큰
    name = ""
    mt = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
                   html, re.IGNORECASE)
    if not mt:
        mt = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if mt:
        head = unescape(_TAG_RE.sub("", mt.group(1)))
        cand = re.split(r"[|·\-–—:\[]", head)[0].strip()
        cand = cand.split()[0] if cand.split() else cand
        if _NAME_RE.match(cand):
            name = cand
    if not name:
        for ln in lines:
            if _looks_like_name(ln):
                name = ln
                break

    # 연락처: 휴대폰(010) 우선, 없으면 첫 전화번호
    phones = _PHONE_RE.findall(text)
    contact = ""
    if phones:
        mobiles = [p for p in phones if re.sub(r"\D", "", p).startswith("01")]
        contact = normalize_phone(mobiles[0] if mobiles else phones[0])

    showroom = _find_showroom(text)
    team_hit = _TEAM_RE.search(text)
    team = (re.sub(r"\s+", "", team_hit.group()) if team_hit
            else team_range_for(showroom))

    if not name and not contact:
        return None
    return StaffMember(name=name, contact=contact, showroom=showroom,
                       team=team, detail_url=detail_url)


def crawl_consultants(
    seeds: Iterable[str] = SEED_LISTING_URLS,
    *,
    session=None,
    save_html_dir: str | Path | None = None,
    delay: float = 0.5,
    max_listing_pages: int = 60,
) -> list[StaffMember]:
    """실제 사이트를 2단계로 수집한다: 목록/지역 페이지 → 개인 상세 페이지.

    사이트 접근이 되는 PC에서 실행. 목록 페이지들을 훑어 consultant-view 링크를
    모두 모은 뒤, 각 상세 페이지를 방문해 이름/연락처/전시장/팀을 추출한다.
    """
    import time

    if session is None:
        from .http_client import build_session
        session = build_session(extra_headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": SALES_HOST + "/sales/consultant-1",
        })

    save_dir = Path(save_html_dir) if save_html_dir else None
    if save_dir:
        save_dir.mkdir(parents=True, exist_ok=True)

    def _save(url: str, html: str) -> None:
        if save_dir:
            slug = re.sub(r"[^\w.-]", "_", url.split("/sales/")[-1]) or "page"
            (save_dir / f"{slug}.html").write_text(html, encoding="utf-8")

    # 1단계: 목록/지역 페이지를 훑어 상세 링크 수집(제한된 스파이더)
    to_visit = list(dict.fromkeys(seeds))
    visited: set[str] = set()
    view_urls: list[str] = []
    view_seen: set[str] = set()

    while to_visit and len(visited) < max_listing_pages:
        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            html = session.get(url).text
        except Exception:  # noqa: BLE001 - 개별 페이지 실패는 건너뜀
            continue
        _save(url, html)
        for v in discover_consultant_view_links(html):
            if v not in view_seen:
                view_seen.add(v)
                view_urls.append(v)
        for link in _discover_listing_links(html):
            if link not in visited and link not in to_visit:
                to_visit.append(link)
        if delay:
            time.sleep(delay)

    if not view_urls:
        raise RuntimeError(
            "상세 페이지(consultant-view) 링크를 찾지 못했습니다. 목록이 JS 로 "
            "렌더링될 수 있습니다. --save-html 로 HTML 을 저장해 확인하거나 "
            "Playwright(browser) 방식으로 확장하세요."
        )

    # 2단계: 각 상세 페이지 방문 → 파싱
    members: list[StaffMember] = []
    for v in view_urls:
        try:
            html = session.get(v).text
        except Exception:  # noqa: BLE001
            continue
        _save(v, html)
        m = parse_detail(html, detail_url=v)
        if m:
            members.append(m)
        if delay:
            time.sleep(delay)

    return dedupe(members)


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
    seen: set[tuple[str, str, str, str]] = set()
    for m in members:
        key = (m.name, m.contact, m.showroom, m.detail_url)
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    return out


# --------------------------------------------------------------------------- #
# 엑셀 내보내기
# --------------------------------------------------------------------------- #

COLUMNS = ["이름", "연락처", "전시장", "팀"]


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
    widths = {"이름": 14, "연락처": 20, "전시장": 24, "팀": 14}
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
