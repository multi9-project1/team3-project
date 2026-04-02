# ============================================================================
# 카카오 API 서비스
# ============================================================================
#
# 이 모듈은 카카오 REST API를 사용하여 다음 기능을 제공합니다:
# 1. 장소 검색 (키워드, 카테고리 기반)
# 2. 숙소/기준 위치 검색 (호텔명, 주소, 좌표)
# 3. 네비게이션 경로 계산 (정확한 거리/시간)
# 4. 장소 상세 정보 크롤링 (운영시간, 리뷰, 평점)
#
# ============================================================================

import requests
from bs4 import BeautifulSoup
from functools import lru_cache
from urllib.parse import parse_qs, quote, unquote, urlparse
from typing import Dict, List, Optional
import re

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    sync_playwright = None
    PLAYWRIGHT_AVAILABLE = False


@lru_cache(maxsize=64)
def _fetch_rendered_place_payload(place_url: str) -> Dict:
    """브라우저 렌더링을 통해 카카오 장소 페이지 본문과 이미지 URL을 가져옵니다."""
    if not PLAYWRIGHT_AVAILABLE or not place_url:
        return {'text': '', 'images': []}

    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(channel='msedge', headless=True)
            except Exception:
                browser = playwright.chromium.launch(headless=True)

            page = browser.new_page()
            page.goto(place_url, wait_until='load', timeout=60000)

            try:
                page.locator('text=장소 기본 정보').first.wait_for(timeout=15000)
            except Exception:
                page.wait_for_timeout(2500)

            body_text = page.locator('body').inner_text(timeout=15000)
            image_urls = page.locator('img').evaluate_all(
                "elements => elements.map((element) => element.currentSrc || element.src || element.getAttribute('src') || '').filter(Boolean)"
            )
            browser.close()

            return {
                'text': body_text,
                'images': image_urls,
            }
    except Exception as exc:
        print(f"렌더링 기반 상세 정보 추출 오류: {exc}")
        return {'text': '', 'images': []}


class KakaoService:
    """
    카카오 API 통합 서비스 클래스
    
    주요 기능:
    - 장소 검색: 키워드, 카테고리 기반 POI 검색
    - 주소 검색: 도로명/지번 주소를 좌표로 변환
    - 경로 계산: 카카오 네비게이션 API로 정확한 거리/시간 계산
    - 상세 정보: 모바일 웹 크롤링으로 운영시간, 리뷰 수집
    """
    
    def __init__(self, api_key: str):
        """
        카카오 서비스 초기화
        
        Args:
            api_key: 카카오 REST API 키 (https://developers.kakao.com)
        """
        self.api_key = (api_key or '').strip()
        self.headers = {'Authorization': f'KakaoAK {self.api_key}'} if self.api_key else {}
        self.base_url = 'https://dapi.kakao.com'
        # 네비게이션 API 엔드포인트
        self.navi_url = 'https://apis-navi.kakaomobility.com'
    
    
    # ========================================================================
    # 🔍 기준 위치 검색 (숙소/출발지)
    # ========================================================================
    
    def search_accommodation(self, query: str) -> Optional[Dict]:
        """
        기준 위치를 검색합니다
        
        다양한 형식 지원:
        - 숙소명: "제주 신라호텔", "하얏트 리젠시"
        - 도로명 주소: "제주시 중앙로 123"
        - 지번 주소: "제주시 연동 312-1"
        - 좌표: "33.4996, 126.5312"
        
        Args:
            query: 검색어
        
        Returns:
            장소 정보 dict 또는 None
            {
                'name': '제주 신라호텔',
                'address': '제주시 연동 312-1',
                'road_address': '제주시 도령로 25',
                'parcel_address': '제주시 연동 312-1',
                'lat': 33.4996,
                'lng': 126.5312,
                'phone': '064-731-7777',
                'place_id': '8322699',
                'place_url': 'http://place.map.kakao.com/8322699',
                'place_type': '호텔',
                'location_note': '카카오 장소 검색으로 찾은 호텔입니다.',
                'search_type': 'keyword'
            }
        """
        cleaned_query = query.strip()
        if not cleaned_query:
            return None
        
        # 1단계: 좌표 형식 체크 (예: "33.4996, 126.5312")
        coordinate_result = self._parse_coordinate_query(cleaned_query)
        if coordinate_result:
            return coordinate_result
        
        # 2단계: 검색 전략 선택 (주소 형태 vs 키워드)
        search_strategies = (
            # 주소 형태이면: 주소 검색 → 일반 검색 → 숙박 검색
            [self._search_address, self._search_general_location, self._search_lodging_by_keyword]
            if self._looks_like_address(cleaned_query)
            # 키워드 형태이면: 숙박 검색 → 일반 검색 → 주소 검색
            else [self._search_lodging_by_keyword, self._search_general_location, self._search_address]
        )
        
        # 3단계: 전략 순서대로 시도
        for strategy in search_strategies:
            result = strategy(cleaned_query)
            if result:
                return result
        
        return None
    
    def _parse_coordinate_query(self, query: str) -> Optional[Dict]:
        """
        입력값이 좌표 형식인지 확인하고 파싱합니다
        
        지원 형식:
        - "33.4996, 126.5312"
        - "33.4996 126.5312"
        - "126.5312, 33.4996" (경도, 위도 순서 - 자동 보정)
        
        Args:
            query: 입력 문자열
        
        Returns:
            좌표 정보 dict 또는 None
        """
        # 정규식: 숫자(소수점 포함), 쉼표 or 공백, 숫자
        match = re.match(
            r'^\s*([+-]?\d+(?:\.\d+)?)\s*(?:,|\s+)\s*([+-]?\d+(?:\.\d+)?)\s*$',
            query
        )
        if not match:
            return None
        
        first_value = float(match.group(1))
        second_value = float(match.group(2))
        lat, lng = first_value, second_value
        
        # 경도/위도 순서 자동 보정
        # (한국 사용자는 경도, 위도 순으로 입력하는 경우가 많음)
        if abs(first_value) > 90 and abs(second_value) <= 90:
            lat, lng = second_value, first_value
        
        # 유효성 검증
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return None
        
        coordinate_label = f"{lat:.6f}, {lng:.6f}"
        return {
            'name': f'입력 좌표 {coordinate_label}',
            'address': coordinate_label,
            'road_address': '',
            'parcel_address': '',
            'lat': lat,
            'lng': lng,
            'phone': '',
            'place_id': '',
            'place_url': '',
            'place_type': '좌표 기준 위치',
            'location_note': '입력한 위도와 경도를 그대로 기준 위치로 사용합니다.',
            'search_type': 'coordinates'
        }
    
    def _looks_like_address(self, query: str) -> bool:
        """
        입력값이 주소 형태인지 판별합니다
        
        판별 기준:
        - 숫자 포함 여부 (번지수)
        - 주소 토큰 포함 여부 (시, 군, 구, 동, 로, 길 등)
        
        Args:
            query: 입력 문자열
        
        Returns:
            주소 형태이면 True
        """
        address_tokens = [
            '특별자치도', '특별시', '광역시', 
            '시', '군', '구', '읍', '면', '동', '리', 
            '로', '길', '번길', '번지'
        ]
        has_number = bool(re.search(r'\d', query))
        has_address_token = any(token in query for token in address_tokens)
        return has_number or has_address_token
    
    def _search_lodging_by_keyword(self, query: str) -> Optional[Dict]:
        """
        숙박 카테고리 기준으로 숙소를 검색합니다
        
        API: /v2/local/search/keyword.json
        카테고리: AD5 (숙박)
        
        Args:
            query: 숙소명 (예: "제주 신라호텔")
        
        Returns:
            숙소 정보 dict 또는 None
        """
        if not self.api_key:
            return None
        
        url = f'{self.base_url}/v2/local/search/keyword.json'
        params = {
            'query': query,
            'category_group_code': 'AD5',  # 숙박 카테고리
            'sort': 'accuracy',            # 정확도순
            'size': 5
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            places = result.get('documents', [])
            
            if not places:
                return None
            
            return self._normalize_accommodation_place(places[0])
        except Exception as e:
            print(f"숙소 검색 오류: {e}")
            return None
    
    def _search_general_location(self, query: str) -> Optional[Dict]:
        """
        일반 키워드 검색으로 기준 위치를 찾습니다
        
        API: /v2/local/search/keyword.json
        
        Args:
            query: 검색어
        
        Returns:
            장소 정보 dict 또는 None
        """
        if not self.api_key:
            return None
        
        url = f'{self.base_url}/v2/local/search/keyword.json'
        params = {
            'query': query,
            'sort': 'accuracy',
            'size': 5
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            places = result.get('documents', [])
            if not places:
                return None
            
            return self._normalize_general_keyword_place(places[0], query)
        except Exception as e:
            print(f"일반 위치 검색 오류: {e}")
            return None
    
    def _search_address(self, query: str) -> Optional[Dict]:
        """
        주소를 좌표로 변환합니다
        
        우선순위:
        1. 카카오 주소 검색 API (API 키 있을 때)
        2. Nominatim (OpenStreetMap) - 백업
        
        Args:
            query: 주소 문자열
        
        Returns:
            좌표 정보 dict 또는 None
        """
        if self.api_key:
            kakao_result = self._search_address_with_kakao(query)
            if kakao_result:
                return kakao_result
        
        return self._search_address_with_nominatim(query)
    
    def _search_address_with_kakao(self, query: str) -> Optional[Dict]:
        """
        카카오 주소 검색 API로 좌표를 찾습니다
        
        API: /v2/local/search/address.json
        
        Args:
            query: 주소 (도로명 또는 지번)
        
        Returns:
            주소 정보 dict 또는 None
        """
        url = f'{self.base_url}/v2/local/search/address.json'
        params = {
            'query': query,
            'analyze_type': 'similar',
            'size': 1
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            documents = result.get('documents', [])
            if not documents:
                return None
            
            return self._normalize_address_result(documents[0], query)
        except Exception as e:
            print(f"주소 검색 오류: {e}")
            return None
    
    def _search_address_with_nominatim(self, query: str) -> Optional[Dict]:
        """
        Nominatim (OpenStreetMap)으로 주소를 검색합니다
        
        카카오 API 백업용 - API 키가 없거나 카카오 검색 실패 시 사용
        
        Args:
            query: 주소
        
        Returns:
            주소 정보 dict 또는 None
        """
        url = 'https://nominatim.openstreetmap.org/search'
        params = {
            'q': query,
            'format': 'jsonv2',
            'limit': 1,
            'countrycodes': 'kr',
            'accept-language': 'ko'
        }
        headers = {
            'User-Agent': 'jeju-travel-recommender/1.0 (local-app)'
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            
            documents = response.json()
            if not documents:
                return None
            
            return self._normalize_nominatim_result(documents[0], query)
        except Exception as e:
            print(f"대체 주소 검색 오류: {e}")
            return None
    
    
    # ========================================================================
    # 🧩 결과 정규화 (API 응답 → 공통 포맷 변환)
    # ========================================================================
    
    def _normalize_accommodation_place(self, place: Dict) -> Dict:
        """
        숙소 검색 결과를 공통 포맷으로 변환합니다
        
        Args:
            place: 카카오 API 응답 (숙박 카테고리)
        
        Returns:
            정규화된 장소 정보 dict
        """
        road_address = place.get('road_address_name', '')
        parcel_address = place.get('address_name', '')
        main_address = road_address or parcel_address
        place_type = self._infer_stay_type(
            place.get('category_name', ''),
            place.get('place_name', '')
        )
        
        return {
            'name': place.get('place_name', ''),
            'address': main_address,
            'road_address': road_address,
            'parcel_address': parcel_address,
            'lat': float(place.get('y', 0)),
            'lng': float(place.get('x', 0)),
            'phone': place.get('phone', ''),
            'place_id': place.get('id', ''),
            'place_url': place.get('place_url', ''),
            'place_type': place_type,
            'location_note': f"카카오 장소 검색으로 찾은 {place_type}입니다.",
            'search_type': 'keyword'
        }
    
    def _normalize_general_keyword_place(self, place: Dict, query: str) -> Dict:
        """
        일반 키워드 검색 결과를 공통 포맷으로 변환합니다
        
        Args:
            place: 카카오 API 응답
            query: 원본 검색어
        
        Returns:
            정규화된 장소 정보 dict
        """
        road_address = place.get('road_address_name', '')
        parcel_address = place.get('address_name', '')
        main_address = road_address or parcel_address or query
        category_full = place.get('category_name', '')
        place_type = category_full.split(' > ')[-1] if category_full else '검색 기준 위치'
        
        return {
            'name': place.get('place_name', '') or query,
            'address': main_address,
            'road_address': road_address,
            'parcel_address': parcel_address,
            'lat': float(place.get('y', 0)),
            'lng': float(place.get('x', 0)),
            'phone': place.get('phone', ''),
            'place_id': place.get('id', ''),
            'place_url': place.get('place_url', ''),
            'place_type': place_type,
            'location_note': '입력한 검색어와 가장 가까운 위치를 기준점으로 사용합니다.',
            'search_type': 'keyword-general'
        }
    
    def _normalize_address_result(self, document: Dict, query: str) -> Dict:
        """
        주소 검색 결과를 공통 포맷으로 변환합니다
        
        Args:
            document: 카카오 주소 API 응답
            query: 원본 주소 문자열
        
        Returns:
            정규화된 주소 정보 dict
        """
        road = document.get('road_address') or {}
        parcel = document.get('address') or {}
        
        road_address = road.get('address_name', '')
        parcel_address = parcel.get('address_name', '')
        main_address = road_address or parcel_address or query
        lat = float(road.get('y') or parcel.get('y') or 0)
        lng = float(road.get('x') or parcel.get('x') or 0)
        building_name = road.get('building_name', '').strip()
        
        location_note = "입력한 주소를 기준 위치로 사용합니다. 숙소명이 없어도 주변 동선을 추천할 수 있어요."
        if road_address and parcel_address and road_address != parcel_address:
            location_note += " 도로명 주소와 지번 주소를 함께 확인할 수 있습니다."
        
        return {
            'name': building_name or query,
            'address': main_address,
            'road_address': road_address,
            'parcel_address': parcel_address,
            'lat': lat,
            'lng': lng,
            'phone': '',
            'place_id': '',
            'place_url': '',
            'place_type': '주소 기준 위치',
            'location_note': location_note,
            'search_type': 'address-kakao'
        }
    
    def _normalize_nominatim_result(self, document: Dict, query: str) -> Dict:
        """
        Nominatim 검색 결과를 공통 포맷으로 변환합니다
        
        Args:
            document: Nominatim API 응답
            query: 원본 주소 문자열
        
        Returns:
            정규화된 주소 정보 dict
        """
        lat = float(document.get('lat', 0))
        lng = float(document.get('lon', 0))
        display_name = document.get('display_name', query)
        
        return {
            'name': query,
            'address': display_name,
            'road_address': '',
            'parcel_address': display_name,
            'lat': lat,
            'lng': lng,
            'phone': '',
            'place_id': '',
            'place_url': '',
            'place_type': '주소 기준 위치',
            'location_note': 'OpenStreetMap 지도 데이터로 주소를 찾았습니다.',
            'search_type': 'address-nominatim'
        }
    
    def _infer_stay_type(self, category_name: str, place_name: str) -> str:
        """
        카테고리와 이름으로 숙소 유형을 추론합니다
        
        Args:
            category_name: 카카오 카테고리 (예: "여행 > 숙박 > 호텔")
            place_name: 장소명
        
        Returns:
            숙소 유형 (호텔, 펜션, 리조트, 게스트하우스, 민박, 숙박)
        """
        combined = (category_name + ' ' + place_name).lower()
        
        if '호텔' in combined or 'hotel' in combined:
            return '호텔'
        elif '펜션' in combined or 'pension' in combined:
            return '펜션'
        elif '리조트' in combined or 'resort' in combined:
            return '리조트'
        elif '게스트하우스' in combined or 'guesthouse' in combined:
            return '게스트하우스'
        elif '민박' in combined:
            return '민박'
        else:
            return '숙박'
    
    
    # ========================================================================
    # 🔍 장소 검색 (카테고리/키워드)
    # ========================================================================
    
    def search_places(
        self,
        query: str = "",
        lat: float = 0,
        lng: float = 0,
        radius_km: int = 10,
        category_code: str = "",
        size: int = 15
    ) -> List[Dict]:
        """
        반경 내 장소를 검색합니다
        
        Args:
            query: 검색어 (선택, 빈 문자열이면 카테고리만 검색)
            lat: 중심 위도
            lng: 중심 경도
            radius_km: 검색 반경 (km)
            category_code: 카카오 카테고리 코드 (FD6: 음식점, CE7: 카페, AT4: 관광지)
            size: 최대 결과 수 (1~15)
        
        Returns:
            장소 리스트
            [
                {
                    'name': '성산일출봉',
                    'category': '관광명소',
                    'lat': 33.458,
                    'lng': 126.942,
                    'address': '제주특별자치도 서귀포시 성산읍...',
                    'phone': '064-783-0959',
                    'distance': 5.2,
                    'place_id': '12345',
                    'place_url': 'http://place.map.kakao.com/12345',
                    'source': 'API'
                },
                ...
            ]
        """
        if not self.api_key:
            return []
        
        # 카테고리 검색 사용 여부
        use_category = bool(category_code and not query)
        
        if use_category:
            url = f'{self.base_url}/v2/local/search/category.json'
            params = {
                'category_group_code': category_code,
                'x': lng,
                'y': lat,
                'radius': radius_km * 1000,  # km → meter
                'sort': 'distance',
                'size': min(size, 15)
            }
        else:
            url = f'{self.base_url}/v2/local/search/keyword.json'
            params = {
                'query': query,
                'x': lng,
                'y': lat,
                'radius': radius_km * 1000,
                'sort': 'distance',
                'size': min(size, 15)
            }
            if category_code:
                params['category_group_code'] = category_code
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            places = result.get('documents', [])
            
            # 결과 정규화
            normalized_places = []
            for place in places:
                normalized = self._normalize_place(place, lat, lng)
                if normalized:
                    normalized_places.append(normalized)
            
            return normalized_places
            
        except Exception as e:
            print(f"장소 검색 오류: {e}")
            return []
    
    def _normalize_place(self, place: Dict, center_lat: float, center_lng: float) -> Optional[Dict]:
        """
        장소 검색 결과를 공통 포맷으로 변환합니다
        
        Args:
            place: 카카오 API 응답
            center_lat: 중심 위도 (거리 계산용)
            center_lng: 중심 경도 (거리 계산용)
        
        Returns:
            정규화된 장소 정보 dict
        """
        place_lat = float(place.get('y', 0))
        place_lng = float(place.get('x', 0))
        
        # 카테고리 정규화
        category_name = place.get('category_name', '')
        category = self._normalize_category(category_name)
        
        # 거리 계산
        distance = calculate_distance(center_lat, center_lng, place_lat, place_lng)
        
        return {
            'name': place.get('place_name', ''),
            'category': category,
            'lat': place_lat,
            'lng': place_lng,
            'address': place.get('address_name', ''),
            'road_address': place.get('road_address_name', ''),
            'phone': place.get('phone', ''),
            'distance': round(distance, 1),
            'place_id': place.get('id', ''),
            'place_url': place.get('place_url', ''),
            'source': 'API'
        }
    
    def _normalize_category(self, category_name: str) -> str:
        """
        카카오 카테고리를 표준 카테고리로 변환합니다
        
        Args:
            category_name: 카카오 카테고리 (예: "음식점 > 한식 > 국수,만두")
        
        Returns:
            표준 카테고리 (맛집, 카페, 관광명소, 기타)
        """
        if not category_name:
            return '기타'
        
        category_lower = category_name.lower()
        
        # 맛집 관련
        if any(keyword in category_lower for keyword in ['음식점', '식당', 'food', '한식', '양식', '일식', '중식']):
            return '맛집'
        
        # 카페 관련
        if any(keyword in category_lower for keyword in ['카페', 'cafe', '디저트', '베이커리']):
            return '카페'
        
        # 관광명소 관련
        if any(keyword in category_lower for keyword in ['관광', '명소', '여행', '문화', '자연', '체험']):
            return '관광명소'
        
        return '기타'
    
    
    # ========================================================================
    # 🚗 네비게이션 경로 계산 (카카오 네비게이션 API)
    # ========================================================================
    
    def get_navigation_route(
        self,
        origin_lat: float,
        origin_lng: float,
        destination_lat: float,
        destination_lng: float
    ) -> Optional[Dict]:
        """
        카카오 네비게이션 API로 정확한 경로 정보를 가져옵니다
        
        ⭐ 이 함수가 실제 카카오맵 네비게이션에서 사용하는 거리/시간을 반환합니다!
        
        API: https://apis-navi.kakaomobility.com/v1/directions
        
        Args:
            origin_lat: 출발지 위도
            origin_lng: 출발지 경도
            destination_lat: 도착지 위도
            destination_lng: 도착지 경도
        
        Returns:
            경로 정보 dict 또는 None (실패 시)
            {
                'distance_km': 15.3,          # 실제 도로 거리 (km)
                'duration_minutes': 25.5,     # 실제 소요 시간 (분)
                'toll_fee': 0,                # 통행료 (원)
                'taxi_fare': 12500,           # 예상 택시비 (원)
                'is_accurate': True           # 정확한 경로인지 여부
            }
        """
        if not self.api_key:
            return None
        
        # 네비게이션 API 엔드포인트
        url = f'{self.navi_url}/v1/directions'
        
        # 요청 파라미터
        params = {
            'origin': f'{origin_lng},{origin_lat}',  # 경도,위도 순서 주의!
            'destination': f'{destination_lng},{destination_lat}',
            'priority': 'RECOMMEND',  # 추천 경로 (속도+거리 균형)
            'car_fuel': 'GASOLINE',   # 휘발유
            'car_hipass': 'false',    # 하이패스 없음
            'alternatives': 'false',  # 대체 경로 불필요
            'road_details': 'false'   # 도로 상세정보 불필요
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # 경로 존재 여부 확인
            routes = data.get('routes', [])
            if not routes:
                return None
            
            # 첫 번째 경로 정보 추출
            route = routes[0]
            summary = route.get('summary', {})
            
            return {
                'distance_km': summary.get('distance', 0) / 1000,  # meter → km
                'duration_minutes': summary.get('duration', 0) / 60,  # second → minute
                'toll_fee': summary.get('fare', {}).get('toll', 0),
                'taxi_fare': summary.get('fare', {}).get('taxi', 0),
                'is_accurate': True  # 카카오 네비게이션 API 사용
            }
            
        except requests.exceptions.HTTPError as e:
            # API 할당량 초과 또는 권한 없음
            if e.response.status_code in [403, 429]:
                print(f"⚠️ 네비게이션 API 사용 불가 (에러 {e.response.status_code})")
                return None
            print(f"네비게이션 API 오류: {e}")
            return None
        except Exception as e:
            print(f"경로 계산 오류: {e}")
            return None
    
    
    # ========================================================================
    # 📋 장소 상세 정보 (크롤링)
    # ========================================================================
    
    @lru_cache(maxsize=100)
    def get_place_details(
        self,
        place_name: str,
        address: str = "",
        phone: str = "",
        place_url: str = "",
        rating: Optional[float] = None,
        review_count: int = 0,
        reviews_text: str = "",
        keywords: str = ""
    ) -> Dict:
        """
        장소의 상세 정보를 크롤링합니다
        
        데이터 출처: 카카오맵 모바일 웹 (m.map.kakao.com)
        
        Args:
            place_name: 장소명
            address: 주소 (매칭 정확도 향상)
            phone: 전화번호 (매칭 정확도 향상)
        
        Returns:
            상세 정보 dict
            {
                'hours': '매일 09:00 - 18:00',
                'is_open': True,            # 현재 영업 중 여부
                'rating': 4.5,              # 평점
                'review_count': 123,        # 리뷰 수
                'photos': ['url1', 'url2'], # 사진 URL 리스트
                'reviews': [],              # 리뷰 (향후 확장)
                'menu': []                  # 메뉴 (향후 확장)
            }
        """
        details = self._empty_details()
        details = self._merge_details(
            details,
            self._build_details_from_csv(rating, review_count, reviews_text, keywords)
        )

        if place_url:
            details = self._merge_details(
                details,
                self._extract_details_from_place_page(place_url)
            )

        # CSV/장소 페이지로 채워지지 않은 값만 검색 결과에서 보완
        if not details.get('hours') or not details.get('photos'):
            details = self._merge_details(
                details,
                self._extract_details_from_mobile_search(place_name, address, phone)
            )

        return details

    def _build_details_from_csv(
        self,
        rating: Optional[float],
        review_count: int,
        reviews_text: str,
        keywords: str
    ) -> Dict:
        """CSV의 평점/리뷰/텍스트 정보를 상세 정보 포맷으로 변환합니다."""
        details = self._empty_details()
        text_blob = ' '.join(filter(None, [str(reviews_text or ''), str(keywords or '')]))

        clean_rating = self._safe_float(rating)
        if clean_rating is not None and clean_rating > 0:
            details['rating'] = clean_rating

        clean_review_count = self._safe_int(review_count)
        parsed_reviews = self._parse_reviews_text(reviews_text)
        details['reviews'] = parsed_reviews
        if clean_review_count > 0:
            details['review_count'] = clean_review_count
        elif parsed_reviews:
            details['review_count'] = len(parsed_reviews)

        details['hours'] = self._extract_hours_from_text(text_blob)
        details['holiday'] = self._extract_holiday_from_text(text_blob)
        details['parking'] = self._extract_parking_from_text(text_blob)

        return details

    def _extract_details_from_mobile_search(
        self,
        place_name: str,
        address: str,
        phone: str
    ) -> Dict:
        """카카오맵 모바일 검색 결과에서 보조 상세 정보를 가져옵니다."""
        search_query = quote(f"{place_name} {address}".strip())
        search_url = f"https://m.map.kakao.com/actions/searchView?q={search_query}"

        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15'
        }

        try:
            response = requests.get(search_url, headers=headers, timeout=10)
            response.raise_for_status()
            response.encoding = 'utf-8'

            soup = BeautifulSoup(response.text, 'html.parser')
            items = soup.select('.searchInfo')
            if not items:
                return self._empty_details()

            candidates = []
            for item in items:
                score = self._calculate_match_score(item, place_name, address, phone)
                if score > 0:
                    candidates.append((score, item))

            if not candidates:
                return self._empty_details()

            candidates.sort(reverse=True, key=lambda x: x[0])
            return self._extract_search_result_details(candidates[0][1])

        except Exception as e:
            print(f"상세 정보 크롤링 오류: {e}")
            return self._empty_details()

    def _extract_details_from_place_page(self, place_url: str) -> Dict:
        """카카오 장소 페이지의 메타데이터에서 대표 사진을 추출합니다."""
        normalized_url = self._normalize_place_url(place_url)
        if not normalized_url:
            return self._empty_details()

        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Referer': normalized_url
        }

        try:
            response = requests.get(normalized_url, headers=headers, timeout=10)
            response.raise_for_status()
            response.encoding = 'utf-8'

            soup = BeautifulSoup(response.text, 'html.parser')
            details = self._empty_details()
            rendered_payload = _fetch_rendered_place_payload(normalized_url)
            rendered_text = rendered_payload.get('text', '')

            details['photos'] = self._extract_rendered_photo_urls(rendered_payload.get('images', []))
            if not details['photos']:
                details['photos'] = self._extract_photo_urls_from_meta(soup)

            details['hours'] = self._extract_hours_from_rendered_text(rendered_text)
            details['holiday'] = self._extract_holiday_from_rendered_text(rendered_text)
            details['parking'] = self._extract_parking_from_rendered_text(rendered_text)

            if '영업 중' in rendered_text:
                details['is_open'] = True
            elif '영업 종료' in rendered_text or '영업종료' in rendered_text:
                details['is_open'] = False

            return details
        except Exception as e:
            print(f"장소 페이지 메타데이터 추출 오류: {e}")
            return self._empty_details()

    def _normalize_place_url(self, place_url: str) -> str:
        """카카오 place URL을 정규화합니다."""
        value = (place_url or '').strip()
        if not value:
            return ''
        if value.startswith('//'):
            return f'https:{value}'
        if value.startswith('http://'):
            return f"https://{value[len('http://'):] }"
        if value.startswith('https://'):
            return value
        return f'https://{value.lstrip('/')}'

    def _extract_photo_urls_from_meta(self, soup: BeautifulSoup) -> List[str]:
        """장소 페이지 meta 태그에서 사진 URL 후보를 추출합니다."""
        photo_urls = []
        meta_keys = [('property', 'og:image'), ('name', 'twitter:image')]

        for attr_name, attr_value in meta_keys:
            tag = soup.find('meta', attrs={attr_name: attr_value})
            if not tag or not tag.get('content'):
                continue

            normalized = self._normalize_image_url(tag.get('content', ''))
            if normalized and 'staticmap' not in normalized:
                photo_urls.append(self._preferred_photo_url(normalized))

        return self._dedupe_photo_urls(photo_urls)

    def _extract_rendered_photo_urls(self, image_urls: List[str]) -> List[str]:
        """렌더링된 페이지의 이미지 목록에서 실제 장소 사진만 추립니다."""
        photos = []
        for image_url in image_urls:
            normalized = self._normalize_image_url(image_url)
            if not normalized:
                continue
            if 'staticmap' in normalized:
                continue
            if 'kakaomapPhoto' not in normalized and 'cthumb' not in normalized:
                continue
            if 'icon_' in normalized or 'parking_line' in normalized:
                continue

            photos.append(self._preferred_photo_url(normalized))

        return self._dedupe_photo_urls(photos)[:6]

    def _preferred_photo_url(self, image_url: str) -> str:
        """썸네일보다 원본 사진 URL을 우선 사용합니다."""
        normalized = self._normalize_image_url(image_url)
        if not normalized:
            return ''

        parsed = urlparse(normalized)
        original_url = parse_qs(parsed.query).get('fname', [''])[0]
        original_url = self._normalize_image_url(unquote(original_url))
        if original_url and 'staticmap' not in original_url:
            return original_url
        return normalized

    def _dedupe_photo_urls(self, photo_urls: List[str]) -> List[str]:
        """같은 사진의 원본/썸네일 중복을 제거합니다."""
        unique_photos = []
        seen = set()

        for photo_url in photo_urls:
            normalized = self._preferred_photo_url(photo_url)
            if not normalized:
                continue

            canonical_key = self._normalize_image_url(normalized)
            if canonical_key in seen:
                continue

            seen.add(canonical_key)
            unique_photos.append(normalized)

        return unique_photos

    def _normalize_image_url(self, image_url: str) -> str:
        """이미지 URL을 https 형태로 정리합니다."""
        value = (image_url or '').strip()
        if not value:
            return ''
        if value.startswith('//'):
            return f'https:{value}'
        if value.startswith('http://'):
            return f"https://{value[len('http://'):] }"
        return value

    def _extract_hours_from_rendered_text(self, text: str) -> str:
        """렌더링된 페이지 본문에서 영업정보 섹션을 추출합니다."""
        section = self._extract_section_text(
            text,
            '영업정보',
            ['URL', '주소', '전화', '인증 매장', '장소 기본 정보', '매장 정보']
        )
        if section:
            return section
        return self._extract_hours_from_text(text)

    def _extract_holiday_from_rendered_text(self, text: str) -> str:
        """렌더링된 페이지 본문에서 휴무 정보를 추출합니다."""
        if not text:
            return ''

        specific_patterns = [
            r'정기휴무\s*[:：]?\s*(?:매주\s*)?(?:월|화|수|목|금|토|일)(?:요일)?',
            r'휴무일\s*[:：]?\s*(?:매주\s*)?(?:월|화|수|목|금|토|일)(?:요일)?'
        ]

        for pattern in specific_patterns:
            match = re.search(pattern, text)
            if match:
                return re.sub(r'\s+', ' ', match.group(0)).strip(' .,:')

        for line in self._normalize_lines(text):
            if '정기휴무' in line or '휴무일' in line:
                return re.sub(r'\s+', ' ', line).strip(' .,:')[:40]

        return self._extract_holiday_from_text(text)

    def _extract_parking_from_rendered_text(self, text: str) -> str:
        """렌더링된 페이지 본문에서 주차 정보를 추출합니다."""
        section = self._extract_section_text(
            text,
            '시설정보',
            ['태그', '메뉴', '예약하기', '전체 후기/평점', '블로그 리뷰']
        )
        if section:
            return section
        return self._extract_parking_from_text(text)

    def _extract_section_text(self, text: str, start_marker: str, stop_markers: List[str]) -> str:
        """텍스트 본문에서 특정 섹션의 핵심 줄을 추출합니다."""
        lines = self._normalize_lines(text)
        start_index = -1

        for index, line in enumerate(lines):
            if line == start_marker:
                start_index = index + 1
                break

        if start_index == -1:
            return ''

        ignored_lines = {
            '펼치기', '수정제안', '복사', '정보 수정 제안하기', '최대 5점',
            '사진/영상 등록 3점, 글 작성 2점'
        }
        collected = []
        for line in lines[start_index:]:
            if line in stop_markers:
                break
            if line in ignored_lines:
                continue
            if any(line.startswith(marker) for marker in stop_markers):
                break
            collected.append(line)
            if len(collected) >= 3:
                break

        filtered = [line for line in collected if line]
        return ' / '.join(filtered[:2])

    def _normalize_lines(self, text: str) -> List[str]:
        """본문 텍스트를 파싱하기 쉬운 줄 목록으로 정리합니다."""
        lines = []
        for raw_line in text.splitlines():
            line = re.sub(r'\s+', ' ', raw_line).strip()
            if not line:
                continue
            line = re.sub(r'([가-힣A-Za-z])(?=\d)', r'\1 ', line)
            line = re.sub(r'(?<=\d)([가-힣A-Za-z])', r' \1', line)
            lines.append(line.strip())
        return lines
    
    def _calculate_match_score(
        self,
        item,
        place_name: str,
        address: str,
        phone: str
    ) -> int:
        """
        검색 결과 항목과 찾는 장소의 매칭 점수를 계산합니다
        
        Args:
            item: BeautifulSoup 검색 결과 항목
            place_name: 찾는 장소명
            address: 찾는 주소
            phone: 찾는 전화번호
        
        Returns:
            매칭 점수 (0~20, 높을수록 일치)
        """
        score = 0
        
        # 제목 매칭 (최대 10점)
        title = item.get('data-title', '') or ''
        if title == place_name:
            score += 10
        elif place_name in title or title in place_name:
            score += 5
        
        # 주소 매칭 (최대 5점)
        if address:
            addr_elem = item.select_one('.txt_g')
            if addr_elem:
                item_addr = addr_elem.get_text(strip=True)
                if address in item_addr or item_addr in address:
                    score += 5
        
        # 전화번호 매칭 (최대 5점)
        if phone:
            item_phone = item.get('data-phone', '') or ''
            if phone == item_phone:
                score += 5
        
        return score
    
    def _extract_search_result_details(self, item) -> Dict:
        """
        HTML 항목에서 상세 정보를 추출합니다
        
        Args:
            item: BeautifulSoup 검색 결과 항목
        
        Returns:
            상세 정보 dict
        """
        details = self._empty_details()
        
        # 대표 이미지
        img = item.select_one('img.img_result')
        if img and img.get('src'):
            img_url = img['src']
            if img_url.startswith('//'):
                img_url = f'https:{img_url}'
            details['photos'].append(img_url)
        
        # 평점
        rating_elem = item.select_one('.num_rate')
        if rating_elem:
            rating_text = rating_elem.get_text(strip=True)
            try:
                details['rating'] = float(rating_text)
            except:
                pass
        
        # 리뷰 수
        info_elem = item.select_one('.info_detail')
        if info_elem:
            info_text = info_elem.get_text()
            review_match = re.search(r'리뷰\s*(\d+)', info_text)
            if review_match:
                details['review_count'] = int(review_match.group(1))
        
        # 영업 상태
        status_elem = item.select_one('.tag_openoff')
        if status_elem:
            status_text = status_elem.get_text(strip=True)
            if '영업중' in status_text:
                details['is_open'] = True
            elif '영업종료' in status_text or '영업 종료' in status_text:
                details['is_open'] = False
        
        # 운영시간
        hours_elem = item.select_one('.txt_openoff')
        if hours_elem:
            details['hours'] = ' '.join(hours_elem.stripped_strings)
        
        return details

    def _parse_reviews_text(self, reviews_text: str) -> List[Dict]:
        """CSV에 저장된 리뷰 문자열을 리스트 형태로 변환합니다."""
        if not reviews_text:
            return []

        reviews = []
        for chunk in str(reviews_text).split('|'):
            text = re.sub(r'\s+', ' ', chunk).strip()
            if not text:
                continue

            date_match = re.search(r'(20\d{2}[./-]\d{1,2}[./-]\d{1,2}\.?)', text)
            reviews.append({
                'text': text[:220],
                'date': date_match.group(1) if date_match else ''
            })

            if len(reviews) >= 8:
                break

        return reviews

    def _extract_hours_from_text(self, text: str) -> str:
        """리뷰 텍스트에서 영업시간 패턴을 추출합니다."""
        if not text:
            return ''

        patterns = [
            r'(?:매일|평일|주말|월|화|수|목|금|토|일)?\s*\d{1,2}:\d{2}\s*[~-]\s*\d{1,2}:\d{2}',
            r'(?:브레이크타임|BT)\s*\d{1,2}:\d{2}\s*[~-]\s*\d{1,2}:\d{2}',
            r'(?:라스트오더|LO)\s*\d{1,2}:\d{2}'
        ]

        matches = []
        for pattern in patterns:
            matches.extend(re.findall(pattern, text, flags=re.IGNORECASE))

        cleaned = self._unique_list([
            re.sub(r'\s+', ' ', match).strip(' .,:')
            for match in matches
            if match and ':' in match
        ])

        return ' / '.join(cleaned[:3])

    def _extract_holiday_from_text(self, text: str) -> str:
        """리뷰 텍스트에서 휴무 정보를 추출합니다."""
        if not text:
            return ''

        patterns = [
            r'정기휴무\s*[:：]?\s*[^|\n,.]{1,30}',
            r'휴무일\s*[:：]?\s*[^|\n,.]{1,30}',
            r'휴무\s*[:：]?\s*[^|\n,.]{1,30}'
        ]

        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return re.sub(r'\s+', ' ', match.group(0)).strip(' .,:')

        return ''

    def _extract_parking_from_text(self, text: str) -> str:
        """리뷰 텍스트에서 주차 관련 문구를 추출합니다."""
        if not text:
            return ''

        snippets = re.findall(r'[^|\n]{0,45}주차[^|\n]{0,45}', text, flags=re.IGNORECASE)
        cleaned = self._unique_list([
            re.sub(r'\s+', ' ', snippet).strip(' .,:')
            for snippet in snippets
            if snippet.strip()
        ])

        return ' / '.join(cleaned[:2])

    def _merge_details(self, base: Dict, extra: Dict) -> Dict:
        """두 상세 정보 dict를 합칩니다."""
        merged = dict(base)
        if not extra:
            return merged

        for key in ['hours', 'holiday', 'parking']:
            if extra.get(key) and not merged.get(key):
                merged[key] = extra[key]

        if extra.get('is_open') is not None and merged.get('is_open') is None:
            merged['is_open'] = extra['is_open']

        if extra.get('rating') is not None and merged.get('rating') is None:
            merged['rating'] = extra['rating']

        merged['review_count'] = max(
            self._safe_int(merged.get('review_count')),
            self._safe_int(extra.get('review_count'))
        )

        merged['photos'] = self._unique_list((merged.get('photos') or []) + (extra.get('photos') or []))
        merged['reviews'] = self._unique_reviews((merged.get('reviews') or []) + (extra.get('reviews') or []))
        merged['menu'] = merged.get('menu') or extra.get('menu') or []

        return merged

    def _unique_list(self, values: List[str]) -> List[str]:
        """순서를 유지하면서 중복 문자열을 제거합니다."""
        result = []
        seen = set()
        for value in values:
            normalized = (value or '').strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result

    def _unique_reviews(self, reviews: List[Dict]) -> List[Dict]:
        """리뷰 목록의 중복을 제거합니다."""
        result = []
        seen = set()
        for review in reviews:
            text = (review or {}).get('text', '').strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append({
                'text': text,
                'date': (review or {}).get('date', '')
            })
        return result[:8]

    def _safe_float(self, value) -> Optional[float]:
        """NaN/문자열을 안전하게 float로 변환합니다."""
        if value in [None, '']:
            return None
        try:
            converted = float(value)
        except (TypeError, ValueError):
            return None
        return None if converted != converted else converted

    def _safe_int(self, value) -> int:
        """NaN/문자열을 안전하게 int로 변환합니다."""
        if value in [None, '']:
            return 0
        try:
            converted = int(float(value))
        except (TypeError, ValueError):
            return 0
        return 0 if converted != converted else converted
    
    def _empty_details(self) -> Dict:
        """
        빈 상세 정보 템플릿을 반환합니다
        
        Returns:
            빈 dict
        """
        return {
            'hours': '',
            'holiday': '',
            'parking': '',
            'is_open': None,
            'rating': None,
            'review_count': 0,
            'photos': [],
            'reviews': [],
            'menu': []
        }


# ============================================================================
# 🔧 헬퍼 함수 (모듈 레벨)
# ============================================================================

def calculate_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    두 좌표 간의 직선 거리를 계산합니다 (Haversine formula)
    
    Args:
        lat1: 첫 번째 지점 위도
        lng1: 첫 번째 지점 경도
        lat2: 두 번째 지점 위도
        lng2: 두 번째 지점 경도
    
    Returns:
        거리 (km)
    
    참고:
    - 실제 도로 거리가 아닌 직선 거리입니다
    - 도로 거리는 get_driving_route() 함수를 사용하세요
    """
    from math import radians, sin, cos, sqrt, atan2
    
    R = 6371  # 지구 반지름 (km)
    
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    
    return R * c


def build_navigation_url(
    origin_name: str,
    origin_lat: float,
    origin_lng: float,
    destination_name: str,
    destination_lat: float,
    destination_lng: float
) -> str:
    """
    카카오맵 길찾기 URL을 생성합니다
    
    Args:
        origin_name: 출발지 이름
        origin_lat: 출발지 위도
        origin_lng: 출발지 경도
        destination_name: 도착지 이름
        destination_lat: 도착지 위도
        destination_lng: 도착지 경도
    
    Returns:
        카카오맵 길찾기 URL
    
    예시:
        https://map.kakao.com/link/from/숙소,33.4996,126.5312/to/성산일출봉,33.458,126.942
    """
    safe_origin = quote(origin_name or '출발지')
    safe_destination = quote(destination_name or '도착지')
    return (
        'https://map.kakao.com/link/from/'
        f'{safe_origin},{origin_lat},{origin_lng}/to/'
        f'{safe_destination},{destination_lat},{destination_lng}'
    )


def estimate_drive_metrics(
    origin_lat: float,
    origin_lng: float,
    destination_lat: float,
    destination_lng: float
) -> Dict:
    """
    직선거리를 바탕으로 차량 이동거리와 시간을 추정합니다
    
    ⚠️ 이 함수는 추정치입니다. 정확한 값은 get_navigation_route()를 사용하세요!
    
    Args:
        origin_lat: 출발지 위도
        origin_lng: 출발지 경도
        destination_lat: 도착지 위도
        destination_lng: 도착지 경도
    
    Returns:
        추정 경로 정보 dict
        {
            'distance_km': 15.6,          # 추정 도로 거리 (직선거리 * 1.25)
            'duration_minutes': 26.0,     # 추정 소요 시간
            'is_accurate': False          # 추정치임을 표시
        }
    
    추정 로직:
    - 도로 거리 = 직선거리 * 1.25
    - 평균 속도:
      - < 5km: 28km/h (시내)
      - 5~15km: 38km/h (도시 외곽)
      - 15~30km: 48km/h (일반 도로)
      - > 30km: 60km/h (간선 도로)
    """
    # 직선 거리 계산
    air_distance_km = calculate_distance(
        origin_lat,
        origin_lng,
        destination_lat,
        destination_lng
    )
    
    # 도로 거리 추정 (직선거리 * 1.25)
    road_distance_km = air_distance_km * 1.25
    
    # 평균 속도 추정 (거리별로 다름)
    if road_distance_km < 5:
        average_speed = 28  # 시내
    elif road_distance_km < 15:
        average_speed = 38  # 도시 외곽
    elif road_distance_km < 30:
        average_speed = 48  # 일반 도로
    else:
        average_speed = 60  # 간선 도로
    
    # 소요 시간 계산
    duration_minutes = (road_distance_km / average_speed) * 60 if road_distance_km else 0
    
    return {
        'distance_km': road_distance_km,
        'duration_minutes': duration_minutes,
        'is_accurate': False  # 추정치임을 명시
    }


def get_driving_route(
    origin_name: str,
    origin_lat: float,
    origin_lng: float,
    destination_name: str,
    destination_lat: float,
    destination_lng: float,
    kakao_api_key: str = ""
) -> Dict:
    """
    차량 기준 이동거리와 시간을 반환합니다
    
    우선순위:
    1. 카카오 네비게이션 API (정확한 값) ⭐
    2. 추정치 (API 사용 불가 시)
    
    Args:
        origin_name: 출발지 이름
        origin_lat: 출발지 위도
        origin_lng: 출발지 경도
        destination_name: 도착지 이름
        destination_lat: 도착지 위도
        destination_lng: 도착지 경도
        kakao_api_key: 카카오 API 키 (선택)
    
    Returns:
        경로 정보 dict
        {
            'distance_km': 15.3,
            'duration_minutes': 25.5,
            'origin_name': '숙소',
            'destination_name': '성산일출봉',
            'navigation_url': 'https://map.kakao.com/link/...',
            'is_accurate': True,  # True: 네비 API, False: 추정치
            'toll_fee': 0,        # 통행료 (네비 API 사용 시)
            'taxi_fare': 12500    # 예상 택시비 (네비 API 사용 시)
        }
    """
    route = None
    
    # 1단계: 카카오 네비게이션 API 시도
    if kakao_api_key and all([origin_lat, origin_lng, destination_lat, destination_lng]):
        kakao = KakaoService(kakao_api_key)
        route = kakao.get_navigation_route(
            origin_lat,
            origin_lng,
            destination_lat,
            destination_lng
        )
    
    # 2단계: 실패 시 추정치 사용
    if route is None:
        route = estimate_drive_metrics(
            origin_lat,
            origin_lng,
            destination_lat,
            destination_lng
        )
    
    # 공통 정보 추가
    route.update({
        'origin_name': origin_name or '출발지',
        'destination_name': destination_name or '도착지',
        'navigation_url': build_navigation_url(
            origin_name,
            origin_lat,
            origin_lng,
            destination_name,
            destination_lat,
            destination_lng
        )
    })
    
    return route
