"""제주 축제 데이터 모음.

이 파일은 앱에서 바로 쓸 수 있는 로컬 축제 카탈로그다.
현재는 2026년 기준으로 확인한 대표 제주 축제 몇 건을 수동 정리해 둔다.

주의:
- 축제 일정은 매년 바뀔 수 있으므로 다음 학기/다음 연도에는 갱신이 필요하다.
- 기간 정보는 2026-04-01 기준 공개 축제 안내 결과를 바탕으로 정리했다.
- 앱에서는 여행 시작일과 일정 일수를 기준으로 "실제 여행 기간과 겹치는 축제"만 추천한다.
"""

from datetime import date, timedelta
from typing import Iterable


JEJU_FESTIVALS_2026 = [
    {
        "name": "서귀포유채꽃축제",
        "category": "축제",
        "address": "제주특별자치도 서귀포시 표선면 가시리 3149-33",
        "lat": 33.3831261752277,
        "lng": 126.736306310049,
        "start_date": date(2026, 4, 4),
        "end_date": date(2026, 4, 5),
        "description": "노란 유채꽃 풍경과 봄 산책 동선이 강점인 계절 축제입니다.",
        "source_note": "2026-04-01 네이버 축제 정보 카드 기준",
    },
    {
        "name": "제주마 입목 문화축제",
        "category": "축제",
        "address": "제주특별자치도 제주시 용강동 제주마방목지 일대",
        "lat": 33.4279240,
        "lng": 126.6046608,
        "start_date": date(2026, 4, 18),
        "end_date": date(2026, 4, 19),
        "description": "제주마와 전통 목축문화를 체험할 수 있는 지역 특화 축제입니다.",
        "source_note": "2026-04-01 네이버 축제 정보 카드 기준",
    },
    {
        "name": "제주들불축제",
        "category": "축제",
        "address": "제주특별자치도 제주시 애월읍 봉성리 산59-8 새별오름 일대",
        "lat": 33.3662542,
        "lng": 126.3577289,
        "start_date": date(2026, 3, 9),
        "end_date": date(2026, 3, 14),
        "description": "제주를 대표하는 대형 봄 축제로, 오름과 야간 불꽃 경관이 핵심 포인트입니다.",
        "source_note": "2026-04-01 네이버 축제 정보 카드 기준",
    },
    {
        "name": "서귀포칠십리축제",
        "category": "축제",
        "address": "제주특별자치도 서귀포시 서귀포시 일대",
        "lat": 33.2535,
        "lng": 126.5600,
        "start_date": date(2026, 10, 23),
        "end_date": date(2026, 10, 25),
        "description": "서귀포 지역 문화와 공연 프로그램이 결합된 가을 지역 축제입니다.",
        "source_note": "2026-04-01 네이버 축제 정보 카드 기준",
    },
]


def trip_end_date(trip_start: date, day_count: int) -> date:
    """여행 시작일과 일수로 종료일을 계산한다."""
    return trip_start + timedelta(days=max(day_count, 1) - 1)


def festival_period_text(festival: dict) -> str:
    """축제 기간을 화면 표기용 문자열로 만든다."""
    start_date = festival["start_date"]
    end_date = festival["end_date"]
    return f"{start_date.isoformat()} ~ {end_date.isoformat()}"


def festival_matches_query(festival: dict, query: str) -> bool:
    """검색어가 축제명/설명에 포함되는지 검사한다."""
    query = str(query or "").strip().lower()
    if not query:
        return True

    haystack = " ".join([
        str(festival.get("name", "")),
        str(festival.get("address", "")),
        str(festival.get("description", "")),
        str(festival.get("category", "")),
    ]).lower()
    return query in haystack


def festival_overlaps_trip(festival: dict, trip_start: date, day_count: int) -> bool:
    """축제 기간과 여행 기간이 겹치는지 검사한다."""
    trip_end = trip_end_date(trip_start, day_count)
    return not (festival["end_date"] < trip_start or festival["start_date"] > trip_end)


def get_active_festivals(trip_start: date, day_count: int, query: str = "") -> list[dict]:
    """여행 기간과 겹치는 축제만 반환한다."""
    active = []
    for festival in JEJU_FESTIVALS_2026:
        if not festival_overlaps_trip(festival, trip_start, day_count):
            continue
        if not festival_matches_query(festival, query):
            continue
        active.append(dict(festival))
    return active


def get_all_festivals() -> Iterable[dict]:
    """전체 축제 목록을 읽기 전용으로 반환한다."""
    return tuple(dict(festival) for festival in JEJU_FESTIVALS_2026)