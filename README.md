# BUTIMI — 캐피탈사 선구매 차량 리스트 수집기

여러 캐피탈사(BNK 등)의 **선구매(선매입) 차량 리스트** 페이지에서 매물 목록을
자동으로 수집해 **CSV / 엑셀**로 내보내는 도구입니다.

- 캐피탈사마다 **어댑터(adapter)** 로 분리 → 사이트가 늘어도 뼈대는 그대로.
- 대부분의 캐피탈사가 `POST → JSON 그리드` 형태라, **코드 수정 없이 설정 파일
  (`config/*.json`)만** 바꿔 대응 가능.
- 첫 번째 대상: **BNK캐피탈** (`config/bnk.json`).

```
python -m butimi list              # 지원 캐피탈사 목록
python -m butimi fetch bnk         # BNK 수집 → output/bnk_YYYYMMDD.csv
python -m butimi fetch bnk --format xlsx
python -m butimi fetch all         # 등록된 모든 캐피탈사
```

---

## ⚠️ 먼저 알아야 할 것 — 실제 요청 정보를 채워야 합니다

이 저장소를 만든 개발 환경은 **네트워크 정책상 캐피탈사 도메인
(`web.bnkcapital.co.kr` 등) 접근이 차단**되어 있습니다. 그래서 실제 API
주소·파라미터·응답 구조를 여기서 직접 확인할 수 없었고, `config/bnk.json`의
`url`·`rows_path`·`field_map` 등은 **자리표시자(placeholder)** 로 채워져 있습니다.

**사이트 접근이 되는 본인 PC**에서 아래 "실제 사이트 연결" 절대로 실제 요청을
한 번 캡처해 `config/bnk.json`에 채워 넣으면 바로 동작합니다. 파싱·페이지네이션·
CSV/엑셀 출력 로직은 이미 완성되어 테스트로 검증돼 있습니다.

---

## 설치

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Python 3.10+ 필요.

---

## 실제 사이트 연결 (BNK 예시)

1. 크롬에서 <https://web.bnkcapital.co.kr/view/prtn/alem/PrtnAlem540M01> 접속.
2. **F12 → Network 탭** 열고, 검색/조회 버튼을 눌러 차량 목록을 갱신.
3. 목록 데이터를 실어오는 요청을 찾습니다. 보통:
   - 타입이 `xhr`/`fetch` 이고,
   - 응답(Response)에 차량 목록 JSON 이 들어 있는 요청.
4. 그 요청을 우클릭 → **Copy → Copy as cURL** (또는 Headers/Payload 탭 확인)해서
   아래 값을 `config/bnk.json`에 옮겨 담습니다.

| config 위치 | 채울 값 |
|---|---|
| `request.url` | 요청 URL (Request URL) |
| `request.method` | `GET` / `POST` |
| `request.body_type` | 폼전송이면 `form`, JSON 바디면 `json`, GET 쿼리면 `query` |
| `request.headers` | `Referer`, 필요시 `X-Requested-With`, 토큰 헤더 등 |
| `request.body` | POST 로 함께 보내는 **고정** 파라미터(검색조건, CSRF 토큰 등) |
| `pagination.page_param` / `size_param` | 페이지 번호·크기를 담는 파라미터 이름 |
| `parse.rows_path` | 응답 JSON 에서 **차량 배열이 있는 위치** (점 표기, 예: `data.list`) |
| `parse.field_map` | 정규화 필드 ← 응답의 실제 키 이름 매핑 |

### `rows_path` 점 표기법

응답이 이런 모양이면:

```json
{ "result": { "vehicles": [ { "carNm": "..." }, ... ] } }
```

→ `rows_path` 는 `"result.vehicles"`. 배열 인덱스도 지원합니다: `data.pages[0].items`.

### `field_map` 작성법

`정규화필드: [응답키 후보들]` 형태입니다. 후보를 여러 개 주면 **값이 있는 첫 번째**를
사용합니다(사이트가 컬럼명을 바꿔도 견딤).

```json
"field_map": {
  "model_name": ["carNm", "modelName"],
  "price":      ["salePrice"],
  "mileage_km": ["distance", "mileage"]
}
```

사용 가능한 정규화 필드: `listing_id, vehicle_no, model_name, trim, year,
first_reg_date, mileage_km, fuel, transmission, color, price, region, status,
posted_at, detail_url`. 매핑 안 한 필드는 빈 칸으로 남고, **원본 응답 전체는
`--include-raw` 로 CSV 에 함께 저장**할 수 있어 나중에 매핑을 보완하기 좋습니다.

> 참고: 개인적으로 캡처한 실제 요청(토큰 포함 가능)은 `config/bnk.local.json` 처럼
> `*.local.json` 으로 저장하면 `.gitignore` 에 의해 커밋되지 않습니다.
> (전용 어댑터 없이 쓸 땐 `BNKAdapter(config_path=...)` 로 경로 지정)

---

## 응답이 JSON 이 아니라 HTML 표라면

일부 사이트는 AJAX 없이 HTML `<table>` 로 목록을 렌더링합니다. 그럴 땐
`src/butimi/adapters/bnk.py` 의 `parse_response()` 오버라이드 예시(주석) 를 해제하고
`pip install beautifulsoup4` 후 셀렉터만 맞추면 됩니다. JS 로 그려지는 사이트는
`playwright` (optional-dependencies `browser`) 로 렌더링 후 파싱하도록 확장할 수 있습니다.

---

## 새 캐피탈사 추가

1. `config/<key>.json` 을 만들고 위와 같이 요청/파싱 설정을 채웁니다.
2. JSON 그리드면 `src/butimi/registry.py` 의 `_CONFIG_ONLY` 에 `<key>` 만 추가 —
   전용 코드가 필요 없습니다.
3. HTML 파싱 등 특수 처리가 필요하면 `adapters/<key>.py` 에 `JsonGridAdapter`
   를 상속한 어댑터를 만들고 `registry._FACTORIES` 에 등록합니다.

---

## 프로젝트 구조

```
src/butimi/
├── models.py            # VehicleListing (공통 정규화 스키마)
├── http_client.py       # 재시도 붙은 requests 세션
├── parsing.py           # JSON 경로 추출 + 필드 매핑
├── exporters.py         # CSV / 엑셀 내보내기
├── registry.py          # 캐피탈사 어댑터 등록/조회
├── cli.py               # python -m butimi ...
└── adapters/
    ├── base.py          # CapitalAdapter, JsonGridAdapter, 설정 스키마
    └── bnk.py           # BNK 어댑터
config/bnk.json          # BNK 요청/파싱 설정 (실제 값으로 채워 사용)
tests/                   # 파싱·수집·내보내기 테스트 (네트워크 불필요)
output/                  # 결과 CSV/엑셀 (gitignore)
```

## 테스트

```bash
pip install -r requirements.txt
PYTHONPATH=src python -m pytest -q
```

네트워크 없이 샘플 데이터(`tests/fixtures/bnk_sample.json`)로 파싱→수집→CSV/엑셀
전 과정을 검증합니다.

---

## 한성자동차 전시장 판매사원 수집 (이름 / 연락처 / 전시장)

메르세데스-벤츠 **한성자동차** 전시장 페이지에서 판매사원의 **이름·연락처·소속
전시장**을 모아 엑셀로 저장하는 별도 수집기입니다.

- 대상: <https://mb.hansung.co.kr/sales/retail-store> → 개별 전시장
  페이지(`/sales/retail-store-<n>`).
- 파서는 **텍스트 기반 휴리스틱**(전화번호를 앵커로 이름을 짝지음)이라 마크업이
  바뀌어도 비교적 견고합니다. 구조가 다르면 `src/butimi/hansung_staff.py` 의
  `parse_staff()` 규칙만 조정하면 됩니다.

```bash
# 사이트 접근이 되는 PC 에서 실행
PYTHONPATH=src python scripts/crawl_hansung_staff.py                 # → output/hansung_staff_YYYYMMDD.xlsx
PYTHONPATH=src python scripts/crawl_hansung_staff.py --format csv
PYTHONPATH=src python scripts/crawl_hansung_staff.py --save-html output/html   # 원본 HTML 함께 저장

# 저장해 둔 HTML 로 오프라인 재파싱
PYTHONPATH=src python scripts/crawl_hansung_staff.py --from-html output/html
```

> ⚠️ 이 저장소를 만든 실행 환경은 네트워크 정책상 `mb.hansung.co.kr` 접근이
> **차단**돼 있어, 여기서는 실제 수집을 실행할 수 없습니다. 위 스크립트를
> **사이트 접근이 되는 본인 PC**에서 돌리면 엑셀이 생성됩니다. 페이지가 JS 로
> 렌더링되어 링크/사원이 안 잡히면 `--save-html` 로 HTML 을 저장해 파서를
> 맞추거나, 저장한 HTML 을 공유해 주세요(파서를 고정해 드립니다).

수집 후, 아직 사원이 안 잡힌 전시장을 자동 점검합니다(사용자가 알려준
`강남/청담 · 삼성 · 서초 · 방배 · 용산 · 강남 자곡 · 인천 송도 · 분당 서현 ·
인천 · 수원 · 안성 · 대전 · 대전 유성 · 원주 · 성남` 전시장 기준).

---

## 유의 / 매너

- 각 캐피탈사 사이트의 **이용약관 / robots.txt** 를 확인하고, 과도한 요청은
  피하세요. `http_client.py` 의 재시도·타임아웃과 `pagination.max_pages` 상한이
  기본 안전장치입니다. 필요하면 요청 간 지연을 추가하세요.
- 수집한 데이터의 활용은 사용자 책임입니다.
