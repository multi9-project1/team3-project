# ============================================================================
# UI 컴포넌트
# ============================================================================
#
# 이 모듈은 Streamlit UI 요소들을 제공합니다:
# 1. 장소 카드 렌더링
# 2. 일정 표시
# 3. 지도 시각화
# 4. 통계 정보
#
# ============================================================================

import streamlit as st
import folium
from streamlit_folium import folium_static
from html import escape
from typing import Dict, List, Optional
from urllib.parse import quote


# ============================================================================
# 🔧 헬퍼 함수
# ============================================================================

def format_duration(minutes: float) -> str:
    """
    분 단위 시간을 읽기 쉬운 텍스트로 변환합니다
    
    Args:
        minutes: 분 단위 시간
    
    Returns:
        포맷된 문자열 (예: "1시간 25분", "45분")
    
    예시:
        format_duration(85) → "1시간 25분"
        format_duration(45) → "45분"
        format_duration(120) → "2시간"
    """
    rounded_minutes = max(0, int(round(minutes)))
    hours, remain_minutes = divmod(rounded_minutes, 60)
    
    if hours and remain_minutes:
        return f"{hours}시간 {remain_minutes}분"
    if hours:
        return f"{hours}시간"
    return f"{remain_minutes}분"


def render_photo_gallery(photos: List[str]):
    """비율이 깨지지 않도록 사진 갤러리를 렌더링합니다."""
    valid_photos = []
    for photo_url in photos:
        normalized = (photo_url or '').strip()
        if normalized and normalized not in valid_photos:
            valid_photos.append(normalized)

    if not valid_photos:
        return

    photo_cols = st.columns(min(len(valid_photos), 3))
    for idx, photo_url in enumerate(valid_photos[:3]):
        safe_url = escape(photo_url, quote=True)
        with photo_cols[idx]:
            st.markdown(
                f"""
                <div style=\"aspect-ratio: 4 / 3; overflow: hidden; border-radius: 12px; background: #f5f5f5; border: 1px solid #e5e7eb; display: flex; align-items: center; justify-content: center;\">
                    <img src=\"{safe_url}\" style=\"width: 100%; height: 100%; object-fit: contain; display: block; background: #f5f5f5;\" referrerpolicy=\"no-referrer\" loading=\"lazy\" />
                </div>
                """,
                unsafe_allow_html=True
            )


# ============================================================================
# 📍 장소 카드 렌더링
# ============================================================================

def render_place_card(
    place: Dict,
    slot_label: str,
    time: str,
    reason: str,
    details: Optional[Dict] = None,
    route_from_previous: Optional[Dict] = None,
    show_refresh: bool = True,
    refresh_key: str = ""
) -> bool:
    """
    장소 정보 카드를 렌더링합니다
    
    Args:
        place: 장소 정보 dict
            - name: 장소명
            - category: 카테고리
            - address: 주소
            - phone: 전화번호
            - distance: 숙소로부터 거리 (km)
            - lat, lng: 좌표
        slot_label: 슬롯 라벨 (예: '☕ 모닝 커피')
        time: 시간대 (예: '08:00-10:00')
        reason: 추천 이유
        details: 상세 정보 (운영시간, 리뷰 등)
        route_from_previous: 이전 장소로부터 경로 정보
        show_refresh: 리프레시 버튼 표시 여부
        refresh_key: 리프레시 버튼 고유 키
    
    Returns:
        리프레시 버튼이 클릭되었는지 여부
    """
    # 기본 정보 추출
    name = place.get('name', '이름없음')
    category = place.get('category', '기타')
    address = place.get('address', '')
    phone = place.get('phone', '')
    distance = place.get('distance', 0)
    lat = place.get('lat', 0)
    lng = place.get('lng', 0)
    
    # 카드 컨테이너
    with st.container():
        # ============================================================
        # 헤더: 슬롯 라벨 + 시간 + 리프레시 버튼
        # ============================================================
        col1, col2 = st.columns([4, 1])
        
        with col1:
            st.markdown(f"### {slot_label} `{time}`")
            st.markdown(f"**{name}** · {category}")
        
        with col2:
            refresh_clicked = False
            if show_refresh:
                if st.button("🔄 다른 곳", key=f"refresh_{refresh_key}"):
                    refresh_clicked = True
        
        # ============================================================
        # 추천 이유
        # ============================================================
        st.info(f"💡 {reason}")
        
        # ============================================================
        # 기본 정보: 주소 + 전화번호
        # ============================================================
        info_cols = st.columns(2)
        with info_cols[0]:
            st.caption(f"📍 {address}")
        with info_cols[1]:
            if phone:
                st.caption(f"📞 {phone}")
        
        # ============================================================
        # 경로 정보 (이전 장소에서 이동 거리/시간)
        # ============================================================
        if route_from_previous:
            distance_km = route_from_previous.get('distance_km', 0)
            duration_min = route_from_previous.get('duration_minutes', 0)
            origin = route_from_previous.get('origin_name', '숙소')
            is_accurate = route_from_previous.get('is_accurate', False)
            
            # 정확도 표시
            accuracy_label = "🎯 카카오내비 추천" if is_accurate else "📏 예상치"
            
            route_text = (
                f"🚗 {origin} → {name} · "
                f"{accuracy_label} · "
                f"{format_duration(duration_min)} · "
                f"{distance_km:.1f}km"
            )
            
            st.caption(route_text)

        if 'distance' in place:
            st.caption(f"📍 숙소 기준 반경 · {distance:.1f}km")
        
        # ============================================================
        # 상세 정보 (접기/펼치기)
        # ============================================================
        if details:
            with st.expander("📋 상세 정보"):
                render_place_details(place, details)
        
        # ============================================================
        # 액션 버튼: 길찾기 + 위치 + 가게정보
        # ============================================================
        button_cols = st.columns(3)
        
        with button_cols[0]:
            # 카카오맵 길찾기
            kakao_url = route_from_previous.get('navigation_url') if route_from_previous else ''
            if not kakao_url:
                kakao_url = f"https://map.kakao.com/link/to/{quote(name)},{lat},{lng}"
            st.link_button("🚗 길찾기", kakao_url)
        
        with button_cols[1]:
            # 위치 표시
            if st.button("📍 위치", key=f"map_{refresh_key}"):
                render_mini_map(lat, lng, name)
        
        with button_cols[2]:
            # 가게 정보 보기 (카카오맵)
            place_url = place.get('place_url', '')
            place_info_url = place_url or f"https://m.map.kakao.com/actions/searchView?q={quote(name)}"
            st.link_button("🏪 가게정보", place_info_url)
        
        st.divider()
        
        return refresh_clicked


def render_place_details(place: Dict, details: Dict):
    """
    장소의 상세 정보를 렌더링합니다
    
    Args:
        place: 장소 정보
        details: 상세 정보 dict
            - hours: 운영시간
            - holiday: 휴무 정보
            - parking: 주차 가능 여부/메모
            - is_open: 현재 영업 여부
            - rating: 평점
            - review_count: 리뷰 수
            - photos: 사진 URL 리스트
            - menu: 메뉴 (있는 경우)
            - reviews: 리뷰 (있는 경우)
    """
    # ================================================================
    # ⏰ 운영 정보
    # ================================================================
    st.markdown("#### ⏰ 운영 정보")
    
    hours = details.get('hours', '')
    holiday = details.get('holiday', '')
    parking = details.get('parking', '')
    is_open = details.get('is_open')
    
    if is_open is True:
        st.success(f"🟢 영업중 · {hours}")
    elif is_open is False:
        st.error(f"🔴 영업종료 · {hours}")
    elif hours:
        st.info(f"ℹ️ {hours}")
    else:
        st.caption("운영 정보 없음")

    if holiday:
        st.caption(f"📅 휴무: {holiday}")

    if parking:
        st.caption(f"🅿️ 주차: {parking}")
    
    # ================================================================
    # ⭐ 평점 및 리뷰 수
    # ================================================================
    rating = details.get('rating')
    review_count = details.get('review_count', 0)
    
    if rating:
        st.markdown("#### ⭐ 평점")
        stars = "⭐" * int(rating)
        st.write(f"{stars} {rating:.1f}/5.0 (리뷰 {review_count}개)")
    
    # ================================================================
    # 📷 사진
    # ================================================================
    photos = details.get('photos', [])
    if photos:
        st.markdown("#### 📷 사진")
        render_photo_gallery(photos)
    
    # ================================================================
    # 🍽️ 메뉴 (있는 경우)
    # ================================================================
    menu = details.get('menu', [])
    if menu:
        st.markdown("#### 🍽️ 메뉴")
        for item in menu:
            st.write(f"- {item.get('name', '')}: {item.get('price', '')}")
    
    # ================================================================
    # 💬 리뷰 (있는 경우)
    # ================================================================
    reviews = details.get('reviews', [])
    if reviews:
        st.markdown("#### 💬 리뷰")
        for review in reviews[:3]:  # 최대 3개
            review_text = review.get('text', '')
            review_date = review.get('date', '')
            if review_text:
                st.caption(f"「{review_text}」 - {review_date}")


def render_mini_map(lat: float, lng: float, name: str):
    """
    작은 지도를 렌더링합니다
    
    Args:
        lat: 위도
        lng: 경도
        name: 장소명
    """
    m = folium.Map(
        location=[lat, lng],
        zoom_start=15,
        tiles='OpenStreetMap'
    )
    
    folium.Marker(
        [lat, lng],
        popup=name,
        tooltip=name,
        icon=folium.Icon(color='red', icon='info-sign')
    ).add_to(m)
    
    folium_static(m, width=300, height=200)


# ============================================================================
# 📅 일정 표시
# ============================================================================

def render_daily_itinerary(
    itinerary: List[Dict],
    all_places,
    data_manager,
    kakao_service,
    stay_name: str = '숙소'
):
    """
    전체 일정을 렌더링합니다
    
    Args:
        itinerary: 일정 리스트
            [
                {
                    'day': 1,
                    'slots': [...]
                },
                ...
            ]
        all_places: 전체 장소 데이터 (리프레시용, 현재 미사용)
        data_manager: 데이터 매니저 (리프레시용, 현재 미사용)
        kakao_service: 카카오 서비스 (상세정보용)
        stay_name: 숙소 이름
    """
    if not itinerary:
        st.info("일정이 생성되지 않았습니다.")
        return
    
    # ================================================================
    # 날짜별 탭 생성
    # ================================================================
    day_tabs = st.tabs([f"📅 {day_info['day']}일차" for day_info in itinerary])
    
    for tab_idx, day_info in enumerate(itinerary):
        with day_tabs[tab_idx]:
            day = day_info['day']
            slots = day_info['slots']
            
            if not slots:
                st.info(f"{day}일차 일정이 없습니다.")
                continue
            
            # ========================================================
            # 이동 정보 요약 (총 이동시간 + 총 거리)
            # ========================================================
            route_overview = day_info.get('route_overview', {})
            if route_overview:
                route_cols = st.columns(2)
                with route_cols[0]:
                    st.metric(
                        "총 차량 이동시간",
                        format_duration(route_overview.get('total_duration_minutes', 0))
                    )
                with route_cols[1]:
                    st.metric(
                        "총 차량 이동거리",
                        f"{route_overview.get('total_distance_km', 0):.1f}km"
                    )

                st.caption("💡 이동 구간은 숙소 → 첫 장소 → 다음 장소 순서의 자동차 기준 거리와 시간입니다.")
                
                # 상세 경로 정보 (선택사항)
                with st.expander("🚗 이동 구간 상세"):
                    segments = route_overview.get('segments', [])
                    for idx, segment in enumerate(segments, start=1):
                        # 정확도 표시
                        source_label = '📏 예상치' if segment.get('is_accurate') == False else '🎯 카카오내비 추천'
                        
                        st.markdown(
                            f"**{idx}구간** {segment.get('origin_name', '출발지')} → {segment.get('destination_name', '도착지')}  \n"
                            f"{source_label} · "
                            f"{format_duration(segment.get('duration_minutes', 0))} · "
                            f"{segment.get('distance_km', 0):.1f}km"
                        )
                    
                    # 예상치가 포함된 경우 안내문
                    if any(segment.get('is_accurate') == False for segment in segments):
                        st.caption("💡 일부 구간은 직선거리 기반 예상치입니다. 실제 소요 시간은 다를 수 있습니다.")
            
            st.divider()
            
            # ========================================================
            # 각 슬롯별 장소 카드
            # ========================================================
            for slot_idx, slot in enumerate(slots):
                place = slot['place']
                
                # 상세 정보 가져오기 (캐싱)
                details = None
                if kakao_service:
                    details = kakao_service.get_place_details(
                        place.get('name', ''),
                        place.get('address', ''),
                                place.get('phone', ''),
                                place.get('place_url', ''),
                                place.get('rating'),
                                place.get('total_cnt', place.get('review_count', 0)),
                                place.get('reviews_text', ''),
                                place.get('keywords', '')
                    )
                
                # 카드 렌더링
                refresh_key = f"day{day}_slot{slot_idx}"
                refresh_clicked = render_place_card(
                    place=place,
                    slot_label=slot['label'],
                    time=slot['time'],
                    reason=slot['reason'],
                    details=details,
                    route_from_previous=slot.get('route_from_previous'),
                    show_refresh=False,  # 리프레시 기능 비활성화 (향후 구현)
                    refresh_key=refresh_key
                )
                
                # 리프레시 버튼 클릭 시 처리 (향후 구현)
                if refresh_clicked:
                    st.info("🔄 새로운 장소를 찾는 중...")
                    # TODO: 리프레시 로직 구현
                    st.rerun()


# ============================================================================
# 🗺️ 전체 지도
# ============================================================================

def render_full_map(
    itinerary: List[Dict],
    user_lat: float,
    user_lng: float,
    user_name: str = "숙소"
):
    """
    전체 일정을 지도에 표시합니다
    
    Args:
        itinerary: 일정 리스트
        user_lat: 숙소 위도
        user_lng: 숙소 경도
        user_name: 숙소 이름
    """
    # ================================================================
    # 지도 초기화 (중심: 숙소)
    # ================================================================
    m = folium.Map(
        location=[user_lat, user_lng],
        zoom_start=11,
        tiles='OpenStreetMap'
    )
    
    # ================================================================
    # 숙소 마커 (빨간색 집 아이콘)
    # ================================================================
    folium.Marker(
        [user_lat, user_lng],
        popup=f"🏠 {user_name}",
        tooltip=user_name,
        icon=folium.Icon(color='red', icon='home')
    ).add_to(m)
    
    # ================================================================
    # 카테고리별 마커 색상 정의
    # ================================================================
    category_colors = {
        '맛집': 'orange',       # 주황색
        '카페': 'lightgray',    # 회색
        '관광명소': 'green'     # 녹색
    }
    
    # 날짜별 경로 색상
    day_route_colors = ['blue', 'purple', 'darkred', 'cadetblue']
    
    # ================================================================
    # 각 일정의 장소 마커 + 경로 선
    # ================================================================
    for day_info in itinerary:
        day = day_info['day']
        
        # 경로 포인트 (숙소 → 각 장소)
        path_points = [[user_lat, user_lng]]
        
        # 각 슬롯별 마커 생성
        for slot in day_info['slots']:
            place = slot['place']
            lat = place.get('lat', 0)
            lng = place.get('lng', 0)
            name = place.get('name', '')
            category = place.get('category', '기타')
            
            # 경로에 포인트 추가
            path_points.append([lat, lng])
            
            # 마커 색상 (카테고리별)
            color = category_colors.get(category, 'blue')
            
            # 팝업 HTML
            popup_html = f"""
            <b>{day}일차 - {slot['label']}</b><br>
            {name}<br>
            {category}
            """
            
            # 마커 추가
            folium.Marker(
                [lat, lng],
                popup=folium.Popup(popup_html, max_width=200),
                tooltip=name,
                icon=folium.Icon(color=color, icon='info-sign')
            ).add_to(m)
        
        # ============================================================
        # 경로 선 (숙소 → 각 장소를 연결)
        # ============================================================
        if len(path_points) > 1:
            route_color = day_route_colors[(day - 1) % len(day_route_colors)]
            folium.PolyLine(
                path_points,
                color=route_color,
                weight=3,
                opacity=0.7,
                tooltip=f'{day}일차 동선'
            ).add_to(m)
    
    # ================================================================
    # 지도 렌더링
    # ================================================================
    folium_static(m, width=1200, height=600)


# ============================================================================
# 📊 통계 정보
# ============================================================================

def render_statistics(itinerary: List[Dict]):
    """
    일정 통계를 렌더링합니다
    
    Args:
        itinerary: 일정 리스트
    
    표시 정보:
    - 총 장소 수
    - 평균 거리
    - 맛집 개수
    - 카페 개수
    - 관광명소 개수
    - 기타 개수
    """
    total_places = sum(len(day_info['slots']) for day_info in itinerary)
    
    # 카테고리별 개수 집계
    category_counts = {
        '맛집': 0,
        '카페': 0,
        '관광명소': 0,
        '기타': 0
    }
    total_segment_distance = 0
    total_segments = 0
    
    for day_info in itinerary:
        for slot in day_info['slots']:
            category = slot['place'].get('category', '기타')
            # 표준 카테고리가 아니면 '기타'로 분류
            if category not in ['맛집', '카페', '관광명소']:
                category = '기타'
            category_counts[category] = category_counts.get(category, 0) + 1

        route_overview = day_info.get('route_overview', {})
        segments = route_overview.get('segments', [])
        total_segment_distance += sum(segment.get('distance_km', 0) for segment in segments)
        total_segments += len(segments)
    
    # ================================================================
    # 통계 표시
    # ================================================================
    st.markdown("### 📊 일정 통계")
    
    # 첫 번째 줄: 총 장소 수, 평균 거리
    cols_row1 = st.columns(2)
    
    with cols_row1[0]:
        st.metric("총 장소 수", f"{total_places}곳")
    
    with cols_row1[1]:
        avg_distance = total_segment_distance / total_segments if total_segments > 0 else 0
        st.metric("평균 구간 이동거리", f"{avg_distance:.1f}km")
    
    # 두 번째 줄: 카테고리별 개수
    cols_row2 = st.columns(4)
    
    with cols_row2[0]:
        st.metric("🍽️ 맛집", f"{category_counts['맛집']}곳")
    
    with cols_row2[1]:
        st.metric("☕ 카페", f"{category_counts['카페']}곳")
    
    with cols_row2[2]:
        st.metric("🏖️ 관광명소", f"{category_counts['관광명소']}곳")
    
    with cols_row2[3]:
        st.metric("🎯 기타", f"{category_counts['기타']}곳")
