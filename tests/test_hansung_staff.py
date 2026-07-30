"""한성자동차 판매사원 파서/내보내기 테스트 (네트워크 불필요)."""

from __future__ import annotations

from pathlib import Path

from butimi import hansung_staff as hs

FIXTURE = Path(__file__).parent / "fixtures" / "hansung_store_sample.html"


def test_parse_staff_extracts_name_contact():
    html = FIXTURE.read_text(encoding="utf-8")
    members = hs.parse_staff(html, showroom="방배 전시장", detail_url="u")

    by_name = {m.name: m for m in members}
    assert set(by_name) == {"김철수", "이영희", "박민수"}

    # 소속 전시장이 모두 채워진다
    assert all(m.showroom == "방배 전시장" for m in members)

    # 첫 전화번호가 정규화되어 연락처로 들어간다(휴대폰 우선)
    assert by_name["김철수"].contact == "010-1234-5678"
    assert by_name["이영희"].contact == "010-2345-6789"  # 직통보다 앞선 휴대폰
    assert by_name["박민수"].contact == "010-3456-7890"  # 점 표기 → 하이픈

    # 개인 팀이 페이지에 없으면 전시장 팀 범위로 채운다
    assert all(m.team == "2팀~마스터팀" for m in members)  # 방배 전시장 범위


def test_per_person_team_detected():
    html = """
      <div><span>정우성</span><span>3팀</span><span>010-1111-2222</span></div>
      <div><span>한지민</span><span>마스터팀</span><span>010-3333-4444</span></div>
    """
    by_name = {m.name: m for m in hs.parse_staff(html, showroom="강남/청담 전시장")}
    assert by_name["정우성"].team == "3팀"
    assert by_name["한지민"].team == "마스터팀"


def test_team_range_lookup_ignores_spacing():
    assert hs.team_range_for("강남/청담 전시장") == "2팀~9팀"
    assert hs.team_range_for("강남청담전시장") == "2팀~9팀"
    assert hs.team_range_for("없는 전시장") == ""


def test_stopwords_not_treated_as_names():
    # 직급/일반 단어는 이름으로 잡히지 않는다
    names = {m.name for m in hs.parse_staff(FIXTURE.read_text(encoding="utf-8"), "s")}
    assert "판매팀장" not in names
    assert "차장" not in names
    assert "메르세데스" not in names


def test_normalize_phone():
    assert hs.normalize_phone("01012345678") == "010-1234-5678"
    assert hs.normalize_phone("02-3479-8600") == "02-3479-8600"
    assert hs.normalize_phone("0234798600") == "02-3479-8600"
    assert hs.normalize_phone("031-710-8000") == "031-710-8000"


def test_discover_store_links():
    list_html = """
      <ul>
        <li><a href="/sales/retail-store-1">강남 전시장</a></li>
        <li><a href="/sales/retail-store-5">방배 전시장</a></li>
        <li><a href="/sales/retail-store-5">방배 전시장</a></li>
        <li><a href="/sales/other">무관 링크</a></li>
      </ul>
    """
    links = hs.discover_store_links(list_html)
    assert links == [
        ("강남 전시장", "https://mb.hansung.co.kr/sales/retail-store-1"),
        ("방배 전시장", "https://mb.hansung.co.kr/sales/retail-store-5"),
    ]


def test_discover_consultant_view_links():
    html = """
      <a href="/sales/consultant-view-1450">전석영 이사</a>
      <a href="https://mb.hansung.co.kr/sales/consultant-view-1187">탁용진 팀장</a>
      <a href="/sales/consultant-view-1450">중복</a>
      <a href="/sales/consultant-1">목록 링크(제외)</a>
    """
    links = hs.discover_consultant_view_links(html)
    assert links == [
        "https://mb.hansung.co.kr/sales/consultant-view-1450",
        "https://mb.hansung.co.kr/sales/consultant-view-1187",
    ]


def test_parse_detail_extracts_name_phone_showroom():
    html = (Path(__file__).parent / "fixtures" / "hansung_consultant_view.html").read_text(
        encoding="utf-8")
    m = hs.parse_detail(html, detail_url="u")
    assert m is not None
    assert m.name == "전석영"
    assert m.contact == "010-9876-5432"      # 전시장 번호가 아닌 휴대폰 우선
    assert m.showroom == "강남/청담 전시장"
    assert m.team == "2팀~9팀"                # 개인 팀 없으니 전시장 범위로 채움


def test_to_xlsx_and_csv(tmp_path):
    members = [
        hs.StaffMember("김철수", "010-1234-5678", "방배 전시장", "2팀~마스터팀"),
        hs.StaffMember("이영희", "010-2345-6789", "방배 전시장", "3팀"),
    ]
    xlsx = hs.to_xlsx(members, tmp_path / "staff.xlsx")
    csv = hs.to_csv(members, tmp_path / "staff.csv")
    assert xlsx.exists() and csv.exists()

    from openpyxl import load_workbook
    ws = load_workbook(xlsx).active
    assert [c.value for c in ws[1]] == ["이름", "연락처", "전시장", "팀"]
    assert ws.max_row == 3  # 헤더 + 2명
    assert ws["D2"].value == "2팀~마스터팀"
