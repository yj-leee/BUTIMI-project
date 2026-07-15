"""BUTIMI — 캐피탈사 선구매 차량 리스트 수집기.

여러 캐피탈사(BNK 등)의 '선구매(선매입) 차량 리스트' 페이지에서 매물 목록을
수집해 CSV/엑셀로 내보내는 도구.

핵심 구성:
    - models.VehicleListing : 캐피탈사 간 공통 정규화 스키마
    - adapters.base.CapitalAdapter : 캐피탈사별 수집 로직 인터페이스
    - adapters.bnk.BNKAdapter : BNK캐피탈 어댑터(설정 파일 기반)
    - exporters : CSV / 엑셀 내보내기
    - cli : 커맨드라인 진입점
"""

__version__ = "0.1.0"
