# recommendation_engine.py
"""
추천 엔진
- 시간대별 자연스러운 일정 생성
- OpenAI를 활용한 개인화 추천
- 개별 장소 리프레시 기능
"""

import pandas as pd
from typing import List, Dict, Optional
from config import TIME_SLOTS
from data_manager import DataManager
from kakao_service import KakaoService, calculate_distance, get_driving_route
import random
import json
import re

# OpenAI 임포트
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None


class RecommendationEngine:
    """여행 코스 추천 엔진"""
    
    def __init__(
        self, 
        data_manager: DataManager,
        kakao_service: Optional[KakaoService] = None,
        openai_api_key: str = None
    ):
        """
        추천 엔진 초기화
        
        Args:
            data_manager: 데이터 매니저 인스턴스
            kakao_service: 카카오 서비스 인스턴스 (선택)
            openai_api_key: OpenAI API 키 (선택, AI 추천 활성화)
        """
        self.data_manager = data_manager
        self.kakao_service = kakao_service
        self.openai_client = None
        
        # OpenAI 클라이언트 초기화
        if openai_api_key and OPENAI_AVAILABLE:
            try:
                self.openai_client = OpenAI(api_key=openai_api_key)
                print("✅ OpenAI 클라이언트 초기화 성공")
            except Exception as e:
                print(f"⚠️ OpenAI 초기화 실패: {e}")
    
    # ========================================================================
    # 일정 생성
    # ========================================================================
    
    def build_itinerary(
        self,
        all_places: pd.DataFrame,
        num_days: int,
        user_lat: float,
        user_lng: float,
        selected_categories: List[str],
        stay_name: str = '숙소',
        user_preferences: str = ""
    ) -> List[Dict]:
        """
        일정을 생성합니다
        
        Args:
            all_places: 전체 장소 데이터
            num_days: 여행 일수
            user_lat: 숙소 위도
            user_lng: 숙소 경도
            selected_categories: 선택한 카테고리 ['맛집', '카페', '관광명소']
            stay_name: 숙소 이름
            user_preferences: 사용자 선호사항 (키워드 기반 추천용)
        
        Returns:
            일정 리스트
            [
                {
                    'day': 1,
                    'slots': [
                        {
                            'slot_type': 'morning_coffee',
                            'label': '☕ 모닝 커피',
                            'time': '08:00-10:00',
                            'place': {...},
                            'reason': '숙소에서 5km로 가까워요'
                        },
                        ...
                    ]
                },
                ...
            ]
        
        알고리즘:
            1. 각 날짜마다 TIME_SLOTS 순서대로 슬롯 생성
            2. 각 슬롯에 맞는 장소 필터링
            3. 거리와 키워드 유사도를 조합하여 추천
            4. 이미 사용한 장소는 제외 (중복 방지)
        """
        itinerary = []
        used_place_ids = set()  # 이미 사용한 장소 추적
        
        for day in range(1, num_days + 1):
            day_slots = []
            current_origin = {
                'name': stay_name,
                'lat': user_lat,
                'lng': user_lng
            }
            
            # 각 시간대별로 장소 추천
            for slot_key, slot_info in TIME_SLOTS.items():
                # 해당 카테고리가 선택되지 않았으면 스킵
                if slot_info['category'] not in selected_categories:
                    continue
                
                # 슬롯에 맞는 장소 찾기
                place = self._find_place_for_slot(
                    all_places,
                    slot_key,
                    used_place_ids,
                    float(current_origin.get('lat', user_lat)),
                    float(current_origin.get('lng', user_lng)),
                    user_preferences  # 사용자 선호사항 전달
                )
                
                if place is not None:
                    # 장소 사용 표시
                    place_id = self._get_place_id(place)
                    used_place_ids.add(place_id)
                    
                    day_slots.append({
                        'slot_type': slot_key,
                        'label': slot_info['label'],
                        'time': slot_info['time'],
                        'place': place,
                        'reason': ""
                    })

                    current_origin = {
                        'name': place.get('name', '다음 장소'),
                        'lat': float(place.get('lat', 0)),
                        'lng': float(place.get('lng', 0))
                    }
            
            if day_slots:  # 슬롯이 하나라도 있으면 추가
                route_overview = self._build_day_route_overview(
                    day_slots,
                    user_lat,
                    user_lng,
                    stay_name
                )

                itinerary.append({
                    'day': day,
                    'slots': day_slots,
                    'route_overview': route_overview
                })
        
        return itinerary
    
    def _find_place_for_slot(
        self,
        all_places: pd.DataFrame,
        slot_type: str,
        used_ids: set,
        user_lat: float,
        user_lng: float,
        user_preferences: str = ""
    ) -> Optional[Dict]:
        """
        특정 슬롯에 맞는 장소를 찾습니다
        
        Args:
            all_places: 전체 장소 데이터
            slot_type: 슬롯 타입 (morning_coffee, lunch 등)
            used_ids: 이미 사용한 장소 ID 세트
            user_lat: 사용자 위도
            user_lng: 사용자 경도
            user_preferences: 사용자 선호사항 (키워드 기반 추천용)
        
        Returns:
            선택된 장소 dict 또는 None
        
        알고리즘:
            1. 슬롯에 맞는 장소 필터링
            2. 이미 사용한 장소 제외
            3. 거리 계산
            4. 키워드 유사도 계산 (user_preferences가 있을 때)
            5. 거리와 유사도를 조합한 점수로 정렬
            6. 최고 점수 장소 선택
        """
        # 슬롯에 맞는 장소 필터링
        filtered = self.data_manager.filter_for_time_slot(
            all_places, 
            slot_type
        )
        
        if filtered.empty:
            return None
        
        # 이미 사용한 장소 제외
        filtered = filtered[
            ~filtered.apply(lambda row: self._get_place_id(row.to_dict()), axis=1).isin(used_ids)
        ]
        
        if filtered.empty:
            return None
        
        # 현재 출발지(숙소 또는 이전 일정) 기준 거리 계산
        filtered = filtered.copy()
        filtered['slot_distance'] = filtered.apply(
            lambda row: calculate_distance(
                user_lat, user_lng, row['lat'], row['lng']
            ),
            axis=1
        )
        
        # 키워드 유사도 기반 점수 계산
        if user_preferences:
            from data_manager import calculate_keyword_similarity
            
            filtered = filtered.copy()
            
            # 각 장소의 키워드 유사도 계산
            filtered['keyword_similarity'] = filtered['keywords'].apply(
                lambda keywords: calculate_keyword_similarity(keywords, user_preferences)
            )
            
            # 거리 점수 계산 (0~1, 가까울수록 높음)
            # 거리 점수 = 1 / (1 + distance/10)
            # - 0km: 1.0
            # - 10km: 0.5
            # - 20km: 0.33
            filtered['distance_score'] = filtered['slot_distance'].apply(
                lambda d: 1.0 / (1.0 + d / 10.0)
            )
            
            # 최종 점수 = (거리 점수 * 0.6) + (키워드 유사도 * 0.4)
            # 거리가 더 중요하지만, 유사도도 고려
            filtered['final_score'] = (
                filtered['distance_score'] * 0.6 + 
                filtered['keyword_similarity'] * 0.4
            )
            
            # 점수순으로 정렬 (높은 점수 우선)
            filtered = filtered.sort_values('final_score', ascending=False)
        else:
            # user_preferences가 없으면 현재 출발지 기준 거리순으로 정렬
            filtered = filtered.sort_values('slot_distance')
        
        # 최상위 장소 선택
        return filtered.iloc[0].to_dict()

    def _build_day_route_overview(
        self,
        day_slots: List[Dict],
        user_lat: float,
        user_lng: float,
        stay_name: str,
        ai_recommended: bool = False
    ) -> Dict:
        """하루 일정의 차량 이동 정보를 계산합니다."""
        segments = []
        total_distance_km = 0.0
        total_duration_minutes = 0.0
        kakao_api_key = self.kakao_service.api_key if self.kakao_service else ""

        previous_stop = {
            'name': stay_name,
            'lat': user_lat,
            'lng': user_lng
        }

        for slot in day_slots:
            current_place = slot['place']
            route_from_previous = get_driving_route(
                previous_stop.get('name', '숙소'),
                float(previous_stop.get('lat', 0)),
                float(previous_stop.get('lng', 0)),
                current_place.get('name', '도착지'),
                float(current_place.get('lat', 0)),
                float(current_place.get('lng', 0)),
                kakao_api_key=kakao_api_key
            )

            slot['route_from_previous'] = route_from_previous

            reference_distance_km = current_place.get('slot_distance')
            if reference_distance_km is None:
                reference_distance_km = calculate_distance(
                    float(previous_stop.get('lat', 0)),
                    float(previous_stop.get('lng', 0)),
                    float(current_place.get('lat', 0)),
                    float(current_place.get('lng', 0))
                )
                current_place['slot_distance'] = reference_distance_km

            slot['reason'] = self._create_reason(
                current_place,
                slot['label'],
                reference_name=previous_stop.get('name', stay_name),
                reference_distance_km=float(reference_distance_km)
            )
            if ai_recommended:
                slot['reason'] = f"{slot['reason']} • AI 추천"

            segments.append(route_from_previous)
            total_distance_km += route_from_previous.get('distance_km', 0)
            total_duration_minutes += route_from_previous.get('duration_minutes', 0)
            previous_stop = current_place

        return {
            'start_name': stay_name,
            'segments': segments,
            'total_distance_km': total_distance_km,
            'total_duration_minutes': total_duration_minutes
        }
    
    def _get_place_id(self, place: Dict) -> str:
        """장소의 고유 ID 생성 (이름 기반)"""
        return str(place.get('name', '') + str(place.get('lat', '')))
    
    def _create_reason(
        self,
        place: Dict,
        slot_label: str,
        reference_name: str = '숙소',
        reference_distance_km: Optional[float] = None
    ) -> str:
        """
        추천 이유를 생성합니다
        
        Args:
            place: 장소 정보
            slot_label: 슬롯 라벨 (예: '☕ 모닝 커피')
            reference_name: 현재 슬롯으로 이동하기 전 출발지 이름
            reference_distance_km: 현재 슬롯의 직전 구간 거리 (직선거리 기준)
        
        Returns:
            추천 이유 문자열
        """
        reasons = []
        
        # 키워드 매칭 이유 (최우선)
        keyword_similarity = place.get('keyword_similarity', 0.0)
        if keyword_similarity > 0.3:  # 유사도 30% 이상이면 강조
            if keyword_similarity > 0.6:
                reasons.append("선호하시는 스타일과 매우 잘 맞아요 ✨")
            else:
                reasons.append("선호하시는 스타일과 잘 맞아요")
        
        # 거리 기준 이유
        distance = reference_distance_km
        if distance is None:
            distance = place.get('slot_distance', place.get('distance', 0))

        reference_name = reference_name or '이전 장소'
        if distance < 5:
            reasons.append(f"{reference_name}에서 {distance:.1f}km로 매우 가까워요")
        elif distance < 15:
            reasons.append(f"{reference_name}에서 {distance:.1f}km 거리에 있어요")
        else:
            reasons.append(f"{reference_name}에서 이동하기 좋은 {distance:.1f}km 거리예요")
        
        # 카테고리별 이유
        category = place.get('category', '')
        if category == '카페':
            if '모닝' in slot_label:
                reasons.append("아침 커피로 시작하기 좋은 곳이에요")
            else:
                reasons.append("여행 중 휴식하기 좋은 카페예요")
        elif category == '맛집':
            if '점심' in slot_label:
                reasons.append("점심 식사로 추천드려요")
            elif '저녁' in slot_label:
                reasons.append("저녁 식사 장소로 적합해요")
            elif '밤' in slot_label:
                reasons.append("저녁 식사 후 가볍게 한잔하기 좋아요")
        elif category == '관광명소':
            if '오전' in slot_label:
                reasons.append("오전 일정으로 추천드리는 관광지예요")
            else:
                reasons.append("오후에 방문하기 좋은 명소예요")
        
        # 출처 표시
        source = place.get('source', 'CSV')
        if source == 'API':
            reasons.append("실시간 검색 결과예요")
        
        return " • ".join(reasons)
    
    # ========================================================================
    # AI 기반 일정 생성 (ChatGPT 활용)
    # ========================================================================
    
    def build_itinerary_with_ai(
        self,
        all_places: pd.DataFrame,
        num_days: int,
        user_lat: float,
        user_lng: float,
        selected_categories: List[str],
        stay_name: str = '숙소',
        user_preferences: str = ""
    ) -> List[Dict]:
        """
        AI를 사용하여 최적화된 일정을 생성합니다
        
        Args:
            all_places: 전체 장소 데이터
            num_days: 여행 일수
            user_lat: 숙소 위도
            user_lng: 숙소 경도
            selected_categories: 선택한 카테고리
            stay_name: 숙소 이름
            user_preferences: 사용자 선호도
        
        Returns:
            AI가 최적화한 일정 리스트
        """
        # AI 사용 불가능하면 기본 추천
        if not self.openai_client:
            print("⚠️ OpenAI 미사용 - 기본 추천으로 전환")
            return self.build_itinerary(
                all_places, num_days, user_lat, user_lng,
                selected_categories, stay_name
            )
        
        try:
            # 1단계: 기본 일정 생성 (거리 + 키워드 기반)
            base_itinerary = self.build_itinerary(
                all_places, num_days, user_lat, user_lng,
                selected_categories, stay_name, user_preferences  # user_preferences 전달
            )
            
            # 2단계: AI에게 최적화 요청
            print("🤖 AI 최적화 시작...")
            optimized = self._optimize_with_ai(
                base_itinerary,
                all_places,
                num_days,
                user_lat,
                user_lng,
                selected_categories,
                stay_name,
                user_preferences
            )
            
            if optimized:
                print("✅ AI 최적화 완료!")
                return optimized
            else:
                print("⚠️ AI 최적화 실패 - 기본 일정 반환")
                return base_itinerary
                
        except Exception as e:
            print(f"❌ AI 추천 오류: {e}")
            return self.build_itinerary(
                all_places, num_days, user_lat, user_lng,
                selected_categories, stay_name, user_preferences  # user_preferences 전달
            )
    
    def _optimize_with_ai(
        self,
        base_itinerary: List[Dict],
        all_places: pd.DataFrame,
        num_days: int,
        user_lat: float,
        user_lng: float,
        selected_categories: List[str],
        stay_name: str,
        user_preferences: str
    ) -> Optional[List[Dict]]:
        """AI를 사용하여 일정을 최적화합니다"""
        
        if not self.openai_client:
            return None
        
        try:
            # AI에게 줄 프롬프트 생성
            prompt = self._build_ai_prompt(
                base_itinerary,
                all_places,
                user_preferences,
                stay_name
            )
            
            # OpenAI API 호출
            print("📡 OpenAI API 호출 중...")
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": """당신은 제주도 여행 전문 AI입니다. 
주어진 장소들을 바탕으로 최적의 여행 일정을 추천해주세요.
동선, 시간대, 카테고리를 고려하여 자연스러운 여행 코스를 만드세요.
반드시 JSON 형식으로만 응답하세요."""
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=2000
            )
            
            # AI 응답 파싱
            ai_response = response.choices[0].message.content
            print(f"🤖 AI 응답 받음: {len(ai_response)} 자")
            
            # JSON 파싱 및 일정 재구성
            optimized = self._parse_ai_response(
                ai_response,
                all_places,
                num_days,
                user_lat,
                user_lng,
                selected_categories,
                stay_name
            )
            
            return optimized
            
        except Exception as e:
            print(f"❌ AI 최적화 오류: {e}")
            return None
    
    def _build_ai_prompt(
        self,
        base_itinerary: List[Dict],
        all_places: pd.DataFrame,
        user_preferences: str,
        stay_name: str
    ) -> str:
        """AI를 위한 프롬프트 생성"""
        
        # 현재 일정 요약
        current_plan = []
        for day_info in base_itinerary:
            day = day_info['day']
            slots = day_info['slots']
            current_plan.append(f"\n{day}일차:")
            for slot in slots:
                place = slot['place']
                current_plan.append(
                    f"  - {slot['label']}: {place.get('name')} "
                    f"({place.get('category')}, 거리 {place.get('distance', 0):.1f}km)"
                )
        
        current_text = "\n".join(current_plan)
        
        # 장소 리스트 (카테고리별로 정리)
        available_by_category = {}
        for category in ['맛집', '카페', '관광명소']:
            category_places = all_places[all_places['category'] == category].head(15)
            places_list = []
            for idx, row in category_places.iterrows():
                places_list.append(
                    f"{row['name']} ({row.get('distance', 0):.1f}km)"
                )
            available_by_category[category] = places_list
        
        prompt = f"""
**현재 일정 (거리 기반 자동 생성):**
{current_text}

**사용 가능한 장소들:**

맛집 ({len(available_by_category['맛집'])}곳):
{chr(10).join(f'  - {p}' for p in available_by_category['맛집'])}

카페 ({len(available_by_category['카페'])}곳):
{chr(10).join(f'  - {p}' for p in available_by_category['카페'])}

관광명소 ({len(available_by_category['관광명소'])}곳):
{chr(10).join(f'  - {p}' for p in available_by_category['관광명소'])}

**숙소:** {stay_name}

**사용자 선호도:** {user_preferences if user_preferences else '특별한 선호도 없음'}

**최적화 요청사항:**
1. 하루 총 이동거리 60km 이내로 조정
2. 가까운 장소들을 묶어서 효율적인 동선 구성
3. 시간대에 맞는 장소 배치 (아침 카페, 점심 식당, 저녁 술집 등)
4. 사용자 선호도 반영
5. 현재 일정을 기반으로 개선

**응답 형식 (JSON):**
각 날짜별로 추천 장소명을 순서대로 배열로 반환하세요.
{{
  "day1": ["장소1", "장소2", "장소3", ...],
  "day2": ["장소4", "장소5", "장소6", ...],
  "day3": ["장소7", "장소8", "장소9", ...]
}}

**중요:** 
- 반드시 위에서 제공된 장소 이름만 사용하세요
- JSON만 반환하고 다른 설명은 하지 마세요
- 각 날짜마다 5~7개 장소 추천
"""
        return prompt
    
    def _parse_ai_response(
        self,
        ai_response: str,
        all_places: pd.DataFrame,
        num_days: int,
        user_lat: float,
        user_lng: float,
        selected_categories: List[str],
        stay_name: str
    ) -> Optional[List[Dict]]:
        """AI 응답을 일정 형식으로 변환"""
        
        try:
            # JSON 추출
            json_match = re.search(r'\{[\s\S]*\}', ai_response)
            if not json_match:
                print("❌ JSON 형식을 찾을 수 없음")
                return None
            
            ai_plan = json.loads(json_match.group())
            print(f"✅ AI 추천 파싱 성공: {len(ai_plan)} 일")
            
            # AI 추천을 실제 일정으로 변환
            itinerary = []
            used_place_ids = set()
            
            for day in range(1, num_days + 1):
                day_key = f"day{day}"
                if day_key not in ai_plan:
                    continue
                
                ai_place_names = ai_plan[day_key]
                day_slots = []
                
                # 각 추천 장소를 시간대 슬롯에 매칭
                slot_idx = 0
                slot_keys = list(TIME_SLOTS.keys())
                
                for place_name in ai_place_names:
                    if slot_idx >= len(slot_keys):
                        break
                    
                    # 장소명으로 데이터 찾기
                    matching_places = all_places[
                        all_places['name'].str.contains(place_name, case=False, na=False)
                    ]
                    
                    if matching_places.empty:
                        continue
                    
                    place_dict = matching_places.iloc[0].to_dict()
                    place_id = self._get_place_id(place_dict)
                    
                    # 이미 사용한 장소는 스킵
                    if place_id in used_place_ids:
                        continue
                    
                    # 시간대 슬롯 찾기
                    slot_key = slot_keys[slot_idx]
                    slot_info = TIME_SLOTS[slot_key]
                    
                    # 카테고리 매칭 확인
                    if slot_info['category'] not in selected_categories:
                        slot_idx += 1
                        continue
                    
                    if slot_info['category'] != place_dict.get('category'):
                        # 카테고리가 안 맞으면 다음 슬롯으로
                        slot_idx += 1
                        if slot_idx >= len(slot_keys):
                            break
                        slot_key = slot_keys[slot_idx]
                        slot_info = TIME_SLOTS[slot_key]
                    
                    # 슬롯 추가
                    used_place_ids.add(place_id)
                    reason = self._create_reason(
                        place_dict,
                        slot_info['label'],
                        user_lat,
                        user_lng
                    )
                    
                    day_slots.append({
                        'slot_type': slot_key,
                        'label': slot_info['label'],
                        'time': slot_info['time'],
                        'place': place_dict,
                        'reason': ""
                    })
                    
                    slot_idx += 1
                
                # 경로 정보 추가
                if day_slots:
                    route_overview = self._build_day_route_overview(
                        day_slots,
                        user_lat,
                        user_lng,
                        stay_name,
                        ai_recommended=True
                    )
                    
                    itinerary.append({
                        'day': day,
                        'slots': day_slots,
                        'route_overview': route_overview
                    })
            
            return itinerary if itinerary else None
            
        except json.JSONDecodeError as e:
            print(f"❌ JSON 파싱 오류: {e}")
            return None
        except Exception as e:
            print(f"❌ AI 응답 처리 오류: {e}")
            return None
    
    # ========================================================================
    # 개별 장소 리프레시 (새로운 추천)
    # ========================================================================
    
    def refresh_place(
        self,
        all_places: pd.DataFrame,
        current_place: Dict,
        slot_type: str,
        used_ids: set,
        user_lat: float,
        user_lng: float
    ) -> Optional[Dict]:
        """
        현재 장소를 새로운 장소로 교체합니다
        
        Args:
            all_places: 전체 장소 데이터
            current_place: 현재 장소
            slot_type: 슬롯 타입
            used_ids: 사용된 장소 ID 세트
            user_lat: 사용자 위도
            user_lng: 사용자 경도
        
        Returns:
            새로운 장소 dict 또는 None
        """
        # 슬롯에 맞는 장소 필터링
        filtered = self.data_manager.filter_for_time_slot(
            all_places,
            slot_type
        )
        
        if filtered.empty:
            return None
        
        # 현재 장소와 이미 사용한 장소 제외
        current_id = self._get_place_id(current_place)
        filtered = filtered[
            ~filtered.apply(
                lambda row: self._get_place_id(row.to_dict()), axis=1
            ).isin(used_ids | {current_id})
        ]
        
        if filtered.empty:
            return None
        
        # 거리 계산 및 정렬
        if 'distance' not in filtered.columns:
            filtered = filtered.copy()
            filtered['distance'] = filtered.apply(
                lambda row: calculate_distance(
                    user_lat, user_lng, row['lat'], row['lng']
                ),
                axis=1
            )
        
        filtered = filtered.sort_values('distance')
        
        # 랜덤하게 선택 (상위 3개 중)
        top_n = min(3, len(filtered))
        candidates = filtered.head(top_n)
        selected_idx = random.randint(0, len(candidates) - 1)
        
        return candidates.iloc[selected_idx].to_dict()
    
    # ========================================================================
    # OpenAI 통합 (선택적)
    # ========================================================================
    
    def enhance_with_ai(
        self,
        itinerary: List[Dict],
        user_preferences: str = ""
    ) -> List[Dict]:
        """
        OpenAI를 사용하여 추천을 개인화합니다
        
        Args:
            itinerary: 기본 일정
            user_preferences: 사용자 선호도 (예: "해산물 좋아함", "오름 선호")
        
        Returns:
            개선된 일정
        
        Note: OpenAI API 키가 필요합니다
        """
        # TODO: OpenAI integration
        # 현재는 기본 일정 그대로 반환
        return itinerary


# ============================================================================
# 헬퍼 함수
# ============================================================================

def format_itinerary_text(itinerary: List[Dict]) -> str:
    """
    일정을 텍스트로 포매팅합니다
    
    Args:
        itinerary: 일정 리스트
    
    Returns:
        포매팅된 텍스트
    
    예시:
        === 1일차 ===
        ☕ 모닝 커피 (08:00-10:00)
        → 카페 XYZ
        
        🌅 오전 관광 (10:00-12:00)
        → 성산일출봉
        ...
    """
    lines = []
    
    for day_info in itinerary:
        day = day_info['day']
        slots = day_info['slots']
        
        lines.append(f"\n=== {day}일차 ===\n")
        
        for slot in slots:
            label = slot['label']
            time = slot['time']
            place_name = slot['place'].get('name', '이름없음')
            
            lines.append(f"{label} ({time})")
            lines.append(f"→ {place_name}\n")
    
    return "\n".join(lines)
