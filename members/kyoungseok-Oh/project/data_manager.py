# data_manager.py
"""
데이터 매니저
- CSV 파일 로딩
- API 데이터와 CSV 데이터 통합
- 카테고리 정규화
"""

import os
import pandas as pd
from typing import List, Dict
import streamlit as st
from config import CATEGORY_MAPPING
from kakao_service import calculate_distance


class DataManager:
    """CSV와 API 데이터를 통합 관리하는 클래스"""
    
    def __init__(self, csv_path: str = None):
        """
        데이터 매니저 초기화
        
        Args:
            csv_path: CSV 파일 경로 (기본: data.csv)
        """
        self.csv_path = csv_path if csv_path else 'data.csv'
        self.df = None

    def _resolve_csv_candidates(self, csv_path: str = None) -> List[str]:
        """사용 가능한 CSV 파일 목록을 우선순위대로 반환합니다."""
        target = csv_path if csv_path else 'data.csv'
        if os.path.exists(target):
            return [target]
        return []

    def _read_csv_with_fallbacks(self, csv_path: str) -> pd.DataFrame:
        """여러 인코딩을 시도하여 CSV를 읽습니다."""
        last_error = None
        for encoding in ['utf-8-sig', 'cp949', 'euc-kr', 'utf-8']:
            try:
                return pd.read_csv(csv_path, encoding=encoding)
            except UnicodeDecodeError as exc:
                last_error = exc
                continue

        if last_error:
            raise last_error

        return pd.read_csv(csv_path)

    def _prepare_dataframe(self, df: pd.DataFrame, csv_path: str) -> pd.DataFrame:
        """data.csv 데이터 구조에 맞춰 표준 포맷으로 정밀하게 정리합니다."""
        prepared = df.copy()

        # 1. 필수 컬럼 확인 및 기본값 생성
        # data.csv에 이미 있는 컬럼: name, category, lat, lng, address, place_url, rating, total_cnt, reviews_text, keywords
        required_cols = ['name', 'category', 'lat', 'lng', 'address']
        for col in required_cols:
            if col not in prepared.columns:
                prepared[col] = ''

        # 2. 누락된 보조 컬럼 생성 (data.csv에 없는 phone, place_id 등)
        optional_cols = ['phone', 'place_url', 'place_id', 'keywords', 'reviews_text']
        for col in optional_cols:
            if col not in prepared.columns:
                prepared[col] = ''

        # 3. 데이터 타입 및 결측치 처리
        prepared['name'] = prepared['name'].fillna('').astype(str).str.strip()
        prepared['address'] = prepared['address'].fillna('').astype(str).str.strip()
        prepared['category'] = prepared['category'].apply(self._normalize_category)
        prepared['phone'] = prepared['phone'].fillna('').astype(str).str.strip()
        prepared['place_url'] = prepared['place_url'].fillna('').astype(str).str.strip()
        prepared['reviews_text'] = prepared['reviews_text'].fillna('').astype(str)
        
        # 숫자형 변환 (에러 발생 시 NaN 처리)
        prepared['lat'] = pd.to_numeric(prepared['lat'], errors='coerce')
        prepared['lng'] = pd.to_numeric(prepared['lng'], errors='coerce')
        prepared['rating'] = pd.to_numeric(prepared['rating'], errors='coerce')
        
        # 리뷰 수 처리 (total_cnt 사용)
        if 'total_cnt' in prepared.columns:
            prepared['total_cnt'] = pd.to_numeric(prepared['total_cnt'], errors='coerce').fillna(0).astype(int)
            prepared['review_count'] = prepared['total_cnt']
        else:
            prepared['review_count'] = 0

        # 4. 키워드(keywords) 정제 로직
        # data.csv의 키워드가 공백 구분인 경우 쉼표 구분으로 변환하여 검색 효율을 높임
        def clean_keywords(row):
            k = str(row['keywords']).strip()
            if not k or k.lower() == 'nan':
                # 키워드가 비어있으면 이름에서 추출
                return self._extract_keywords_from_name(row['name'])
            # 공백으로 구분된 단어들을 쉼표로 변환
            words = k.replace(',', ' ').split()
            return ','.join(dict.fromkeys(words)) # 중복 제거 포함

        prepared['keywords'] = prepared.apply(clean_keywords, axis=1)

        # 5. 메타데이터 추가 및 불필요한 행 제거
        prepared['source'] = 'CSV'
        prepared['source_file'] = os.path.basename(csv_path)

        # 위도/경도가 없거나 이름이 없는 데이터는 추천이 불가능하므로 제거
        prepared = prepared.dropna(subset=['lat', 'lng'])
        prepared = prepared[prepared['name'] != '']

        return prepared.reset_index(drop=True)
    
    # ========================================================================
    # CSV 데이터 로딩
    # ========================================================================
    
    @st.cache_data(ttl=3600)  # 1시간 캐싱
    def load_csv(_self) -> pd.DataFrame:
        """data.csv 하나만 타겟팅하여 로드합니다."""
        if not os.path.exists(_self.csv_path):
            st.error(f"⚠️ '{_self.csv_path}' 파일을 찾을 수 없습니다.")
            return pd.DataFrame()

        try:
            # 질문하신 함수들을 호출하여 데이터를 읽고 가공합니다.
            loaded = _self._read_csv_with_fallbacks(_self.csv_path)
            prepared = _self._prepare_dataframe(loaded, _self.csv_path)
            
            # 최종 중복 제거
            df = prepared.drop_duplicates(subset=['name'], keep='first').reset_index(drop=True)
            _self.df = df
            return df
        except Exception as e:
            st.error(f"데이터 로드 중 오류 발생: {e}")
            return pd.DataFrame()
    
    def _normalize_category(self, category: str) -> str:
        """
        CSV 카테고리를 표준 카테고리로 변환
        
        자연/문화 → 관광명소
        음식점/한식/양식 → 맛집
        카페/디저트 → 카페
        """
        if pd.isna(category) or not category:
            return '기타'
        
        category = str(category).strip()
        
        # 매핑 테이블에서 찾기
        for key, value in CATEGORY_MAPPING.items():
            if key in category:
                return value
        
        # 매핑되지 않으면 원본 반환
        return category
    
    def _extract_keywords_from_name(self, name: str) -> str:
        """
        장소명에서 키워드를 자동 추출합니다
        
        Args:
            name: 장소명
        
        Returns:
            쉼표로 구분된 키워드 문자열
        
        예시:
            "성산일출봉" → "성산,일출봉,일출,오름"
            "제주흑돼지거리" → "제주,흑돼지,거리,고기"
            "애월한담해변카페" → "애월,한담,해변,카페,오션뷰"
        """
        if pd.isna(name) or not name:
            return ''
        
        name = str(name).strip()
        keywords = [name]  # 전체 이름도 키워드로
        
        # 일반적인 키워드 패턴
        keyword_patterns = {
            # 자연/관광
            '일출': ['일출', '아침', '경관'],
            '폭포': ['폭포', '자연', '경관'],
            '해변': ['해변', '바다', '오션뷰'],
            '오름': ['오름', '등산', '경관'],
            '산': ['산', '등산', '자연'],
            '굴': ['동굴', '자연'],
            '해수욕장': ['해수욕장', '바다', '해변'],
            
            # 음식
            '흑돼지': ['흑돼지', '고기', '구이'],
            '해녀': ['해녀', '해산물', '전복'],
            '국수': ['국수', '면', '점심'],
            '해장국': ['해장국', '국밥', '점심'],
            '카페': ['카페', '커피', '디저트'],
            '맛집': ['맛집', '식당'],
            
            # 문화
            '민속': ['민속', '문화', '전통'],
            '박물관': ['박물관', '문화', '전시'],
            '미술관': ['미술관', '예술', '전시'],
        }
        
        # 패턴 매칭
        for pattern, related_keywords in keyword_patterns.items():
            if pattern in name:
                keywords.extend(related_keywords)
        
        # 중복 제거
        keywords = list(set(keywords))
        
        return ','.join(keywords)
    
    # ========================================================================
    # 데이터 필터링
    # ========================================================================
    
    def filter_by_location(
        self, 
        df: pd.DataFrame, 
        center_lat: float, 
        center_lng: float, 
        radius_km: int
    ) -> pd.DataFrame:
        """
        중심 좌표로부터 반경 내의 장소만 필터링
        
        Args:
            df: 데이터프레임
            center_lat: 중심 위도
            center_lng: 중심 경도
            radius_km: 반경 (km)
        
        Returns:
            필터링된 데이터프레임 (distance 컬럼 추가)
        """
        if df.empty:
            return df
        
        # 거리 계산
        df = df.copy()
        df['distance'] = df.apply(
            lambda row: calculate_distance(
                center_lat, center_lng, 
                row['lat'], row['lng']
            ),
            axis=1
        )
        
        # 반경 내 필터링
        df = df[df['distance'] <= radius_km]
        
        # 거리순 정렬
        df = df.sort_values('distance').reset_index(drop=True)
        
        return df
    
    def filter_by_categories(
        self, 
        df: pd.DataFrame, 
        categories: List[str]
    ) -> pd.DataFrame:
        """
        선택한 카테고리만 필터링
        
        Args:
            df: 데이터프레임
            categories: 카테고리 리스트 (예: ['맛집', '카페'])
        
        Returns:
            필터링된 데이터프레임
        """
        if df.empty or not categories:
            return df
        
        return df[df['category'].isin(categories)].reset_index(drop=True)
    
    # ========================================================================
    # CSV + API 데이터 통합
    # ========================================================================
    
    def merge_with_api_data(
        self, 
        csv_df: pd.DataFrame, 
        api_places: List[Dict]
    ) -> pd.DataFrame:
        """
        CSV 데이터와 API 데이터를 통합
        
        Args:
            csv_df: CSV 데이터프레임
            api_places: API 검색 결과 리스트
        
        Returns:
            통합된 데이터프레임 (중복 제거, source 컬럼으로 출처 표시)
        """
        if not api_places:
            return csv_df
        
        # API 데이터를 DataFrame으로 변환
        api_df = pd.DataFrame(api_places)
        
        # 컬럼 통일
        for col in ['phone', 'place_url', 'place_id', 'rating', 'total_cnt', 'review_count', 'reviews_text', 'source_file']:
            if col not in csv_df.columns:
                csv_df[col] = ''
            if col not in api_df.columns:
                api_df[col] = ''
        
        # 통합
        combined = pd.concat([csv_df, api_df], ignore_index=True)
        
        # 중복 제거 (이름 기준, CSV 우선)
        combined = combined.drop_duplicates(subset=['name'], keep='first')
        
        # 거리순 정렬
        if 'distance' in combined.columns:
            combined = combined.sort_values('distance').reset_index(drop=True)
        
        return combined
    
    # ========================================================================
    # 시간대별 필터링 (자연스러운 추천을 위해)
    # ========================================================================
    
    def filter_for_time_slot(
        self, 
        df: pd.DataFrame, 
        slot_type: str,
        query: str = ''
    ) -> pd.DataFrame:
        """
        시간대에 맞는 장소만 필터링
        
        Args:
            df: 데이터프레임
            slot_type: 슬롯 타입 (morning_coffee, lunch, dinner, night_drink 등)
            query: 검색 키워드
        
        Returns:
            필터링된 데이터프레임
        
        예시:
            - morning_coffee: 카페만
            - lunch: 점심 적합한 식당 (국수, 백반 등)
            - dinner: 저녁/고기 식당
            - night_drink: 술집
        """
        if df.empty:
            return df
        
        result = df.copy()
        
        # 슬롯 타입별 필터링
        if slot_type == 'morning_coffee':
            # 카페만
            result = result[result['category'] == '카페']
        
        elif slot_type == 'lunch':
            # 점심 적합한 맛집 (술집 제외)
            result = result[result['category'] == '맛집']
            # 술집 키워드 제외
            drink_keywords = ['술집', '주점', '포차', '호프', '바', 'bar', 'pub']
            for keyword in drink_keywords:
                result = result[~result['name'].str.contains(keyword, na=False)]
        
        elif slot_type == 'dinner':
            # 저녁 식사 (고기, 해산물, 치킨 등)
            result = result[result['category'] == '맛집']
        
        elif slot_type == 'night_drink':
            # 술집만
            drink_keywords = ['술집', '주점', '포차', '호프', '바', 'bar', 'pub', '이자카야']
            mask = result['name'].str.contains('|'.join(drink_keywords), na=False)
            result = result[mask]
        
        elif slot_type in ['morning_activity', 'afternoon_activity']:
            # 관광명소만
            result = result[result['category'] == '관광명소']
        
        elif slot_type == 'cafe_break':
            # 카페 (오후 휴식)
            result = result[result['category'] == '카페']
        
        # 검색 키워드 필터링
        if query:
            query_lower = query.lower()
            mask = (
                result['name'].str.lower().str.contains(query_lower, na=False) |
                result['address'].str.lower().str.contains(query_lower, na=False)
            )
            result = result[mask]
        
        return result.reset_index(drop=True)


# ============================================================================
# 헬퍼 함수
# ============================================================================

def get_place_summary(place: Dict) -> str:
    """
    장소 정보를 요약 문자열로 반환
    
    Args:
        place: 장소 dict
    
    Returns:
        "성산일출봉 (관광명소, 5.2km)"
    """
    name = place.get('name', '이름없음')
    category = place.get('category', '기타')
    distance = place.get('distance', 0)
    
    return f"{name} ({category}, {distance:.1f}km)"


def calculate_keyword_similarity(place_keywords: str, user_preferences: str) -> float:
    """
    장소 키워드와 사용자 선호사항 간의 유사도를 계산합니다
    
    Args:
        place_keywords: 장소의 키워드 문자열 (쉼표 구분)
        user_preferences: 사용자 선호사항 텍스트
    
    Returns:
        유사도 점수 (0.0 ~ 1.0)
        - 1.0: 완벽한 매치
        - 0.0: 전혀 매치 안됨
    
    알고리즘:
        1. 장소 키워드와 사용자 선호사항을 단어 단위로 분리
        2. 공통 단어 개수 계산
        3. 유사도 = 공통 단어 수 / max(장소 키워드 수, 사용자 단어 수)
    
    예시:
        place_keywords = "해산물,회,전복,오션뷰"
        user_preferences = "해산물 좋아하고 오션뷰 카페 선호"
        → 공통: "해산물", "오션뷰" (2개)
        → 유사도: 2 / 4 = 0.5
    """
    if not place_keywords or not user_preferences:
        return 0.0
    
    # 키워드 정제
    place_keywords = str(place_keywords).lower().strip()
    user_preferences = str(user_preferences).lower().strip()
    
    # 단어 집합 생성
    place_words = set()
    for keyword in place_keywords.split(','):
        keyword = keyword.strip()
        if keyword:
            place_words.add(keyword)
            # 부분 단어도 추가 (예: "흑돼지" → "돼지", "고기")
            if len(keyword) > 2:
                place_words.add(keyword[:-1])  # 마지막 글자 제거
                place_words.add(keyword[1:])   # 첫 글자 제거
    
    # 사용자 선호사항 단어 집합
    user_words = set()
    # 쉼표, 공백, 구두점으로 분리
    import re
    words = re.split(r'[,\s.!?]+', user_preferences)
    for word in words:
        word = word.strip()
        if len(word) >= 2:  # 2글자 이상만
            user_words.add(word)
            # 부분 단어도 추가
            if len(word) > 2:
                user_words.add(word[:-1])
                user_words.add(word[1:])
    
    # 공통 단어 계산
    common_words = place_words & user_words
    
    if not common_words:
        return 0.0
    
    # 유사도 계산
    # 공통 단어 수 / 전체 단어 수 (중복 제거)
    total_words = len(place_words | user_words)
    similarity = len(common_words) / total_words if total_words > 0 else 0.0
    
    return min(similarity, 1.0)  # 최대 1.0
