# ============================================================================
# 제주 여행 맞춤 추천 시스템 - 메인 앱
# ============================================================================
#
# 실행 방법:
#     streamlit run app.py
#
# 주요 기능:
#     1. 숙소/기준 위치 검색 (호텔명, 주소, 좌표)
#     2. 시간대별 자연스러운 일정 생성
#     3. AI 기반 최적화 (OpenAI API)
#     4. 정확한 경로 계산 (카카오 네비게이션 API)
#     5. 상세 정보 제공 (운영시간, 리뷰, 평점)
#
# ============================================================================

import streamlit as st
import pandas as pd
from config import (
    PAGE_CONFIG, DISPLAY_CATEGORIES, TRAVEL_DAYS,
    DEFAULT_RADIUS, KAKAO_API_KEY, OPENAI_API_KEY, MESSAGES
)
from kakao_service import KakaoService
from data_manager import DataManager
from recommendation_engine import RecommendationEngine
from ui_components import (
    render_daily_itinerary, render_full_map, render_statistics
)


# ============================================================================
# 📱 페이지 설정
# ============================================================================

st.set_page_config(**PAGE_CONFIG)


# ============================================================================
# 💾 세션 상태 초기화
# ============================================================================

def init_session_state():
    """
    세션 상태를 초기화합니다
    
    세션 변수:
    - kakao_api_key: 카카오 API 키 (.env에서 로드)
    - openai_api_key: OpenAI API 키 (.env에서 로드)
    - itinerary: 생성된 여행 일정
    - all_places: 검색된 전체 장소 데이터
    - user_location: 선택된 기준 위치 (숙소)
    """
    if 'kakao_api_key' not in st.session_state:
        st.session_state.kakao_api_key = KAKAO_API_KEY
    
    if 'openai_api_key' not in st.session_state:
        st.session_state.openai_api_key = OPENAI_API_KEY
    
    if 'itinerary' not in st.session_state:
        st.session_state.itinerary = []
    
    if 'all_places' not in st.session_state:
        st.session_state.all_places = pd.DataFrame()
    
    if 'user_location' not in st.session_state:
        st.session_state.user_location = None

init_session_state()


# ============================================================================
# 🎛️ 사이드바 - 설정
# ============================================================================

with st.sidebar:
    st.markdown("## ⚙️ 설정")
    
    # ================================================================
    # API 상태 표시
    # ================================================================
    with st.expander("🔑 API 상태", expanded=False):
        if st.session_state.get('kakao_api_key'):
            st.success("✅ 카카오 API: 설정됨")
        else:
            st.warning("⚠️ 카카오 API: 설정 안됨")
        
        if st.session_state.get('openai_api_key'):
            st.success("✅ OpenAI API: 설정됨 (AI 추천 가능)")
        else:
            st.info("ℹ️ OpenAI API: 설정 안됨 (기본 추천만 가능)")
        
        st.caption("💡 API 키는 .env 파일에서 관리됩니다")
    
    st.divider()
    
    # ================================================================
    # 📍 기준 위치 검색
    # ================================================================
    st.markdown("### 📍 기준 위치")
    
    search_query = st.text_input(
        "숙소명, 주소 또는 좌표",
        placeholder="예: 제주 신라호텔, 제주시 연동 312-1, 33.4996, 126.5312",
        help="숙소명, 도로명 주소, 지번 주소, 위도/경도를 모두 기준 위치로 사용할 수 있습니다"
    )
    
    if not st.session_state.get('kakao_api_key'):
        st.caption("💡 카카오 API 키가 없어도 주소나 좌표를 기준 위치로 설정하고 CSV 데이터로 추천할 수 있습니다.")
    
    if st.button("🔍 기준 위치 설정", use_container_width=True):
        if not search_query:
            st.warning("검색어를 입력해주세요")
        else:
            with st.spinner("기준 위치를 확인하는 중..."):
                kakao = KakaoService(st.session_state.get('kakao_api_key', ''))
                result = kakao.search_accommodation(search_query)
                
                if result:
                    st.session_state.user_location = result
                    search_type = result.get('search_type', '')
                    if search_type == 'coordinates':
                        st.success("✅ 입력한 좌표를 기준 위치로 설정했습니다!")
                    elif search_type.startswith('address'):
                        st.success("✅ 입력한 주소를 기준 위치로 설정했습니다!")
                    else:
                        st.success(
                            f"✅ {result['name']} ({result.get('place_type', '기준 위치')})를 기준 위치로 설정했습니다!"
                        )
                    st.rerun()
                else:
                    st.error("😥 위치를 찾지 못했습니다. 주소를 더 자세히 입력하거나 위도, 경도를 직접 입력해주세요.")
    
    # ================================================================
    # 선택된 기준 위치 표시
    # ================================================================
    if st.session_state.user_location:
        loc = st.session_state.user_location
        st.success(f"📍 {loc['name']}")
        st.caption(f"유형: {loc.get('place_type', '기준 위치')}")
        st.caption(f"좌표: {loc.get('lat', 0):.6f}, {loc.get('lng', 0):.6f}")
        
        if loc.get('address'):
            st.caption(f"기준 주소: {loc['address']}")
        if loc.get('road_address') and loc['road_address'] != loc.get('address'):
            st.caption(f"도로명 주소: {loc['road_address']}")
        if loc.get('parcel_address') and loc['parcel_address'] != loc.get('address'):
            st.caption(f"지번 주소: {loc['parcel_address']}")
        if loc.get('location_note'):
            st.caption(f"설명: {loc['location_note']}")
        
        if st.button("🗑️ 기준 위치 초기화"):
            st.session_state.user_location = None
            st.session_state.itinerary = []
            st.rerun()
    
    st.divider()
    
    # ================================================================
    # 📅 여행 일정 설정
    # ================================================================
    st.markdown("### 📅 여행 일정")
    travel_days = st.selectbox(
        "여행 기간",
        options=list(TRAVEL_DAYS.keys()),
        index=2  # 기본값: 2박 3일
    )
    num_days = TRAVEL_DAYS[travel_days]
    
    # ================================================================
    # 📏 검색 반경 설정
    # ================================================================
    st.markdown("### 📏 검색 반경")
    radius_km = st.slider(
        "숙소로부터 반경 (km)",
        min_value=5,
        max_value=50,
        value=DEFAULT_RADIUS,
        step=5
    )
    
    # ================================================================
    # 🏷️ 카테고리 선택
    # ================================================================
    st.markdown("### 🏷️ 카테고리")
    selected_categories = []
    for category in DISPLAY_CATEGORIES.keys():
        if st.checkbox(category, value=True):
            selected_categories.append(category)
    
    st.divider()
    
    # ================================================================
    # 🤖 AI 추천 옵션 (OpenAI API 키가 있을 때만)
    # ================================================================
    use_ai = False
    user_preferences = ""
    
    if st.session_state.get('openai_api_key'):
        st.markdown("### 🤖 AI 맞춤 추천")
        use_ai = st.checkbox(
            "AI 기반 최적화 사용",
            value=True,
            help="ChatGPT가 동선과 시간대를 고려하여 최적의 코스를 추천합니다"
        )
        
        if use_ai:
            user_preferences = st.text_area(
                "선호 사항 (선택)",
                placeholder="예: 해산물 좋아함, 자연 경관 중심, 카페는 오션뷰 선호",
                help="AI가 당신의 취향을 반영하여 추천합니다",
                height=80
            )
        
        st.divider()
    
    # ================================================================
    # 🎯 추천 버튼
    # ================================================================
    recommend_btn = st.button(
        "🎯 추천 코스 생성",
        use_container_width=True,
        type="primary"
    )


# ============================================================================
# 🏠 메인 영역
# ============================================================================

# ====================================================================
# 헤더
# ====================================================================
st.markdown("""
<div style='text-align: center'>
    <h1>🏝️ 제주 여행 맞춤 추천</h1>
    <p>숙소 위치와 선호도에 맞는 자연스러운 여행 코스를 추천해드립니다</p>
</div>
""", unsafe_allow_html=True)

st.divider()


# ====================================================================
# 추천 코스 생성 로직
# ====================================================================

if recommend_btn:
    # ================================================================
    # 입력 검증
    # ================================================================
    if not st.session_state.user_location:
        st.error("⚠️ 먼저 기준 위치를 설정해주세요!")
    elif not selected_categories:
        st.error("⚠️ 최소 하나의 카테고리를 선택해주세요!")
    else:
        with st.spinner(MESSAGES['loading']):
            # ========================================================
            # 1단계: 데이터 로딩
            # ========================================================
            data_manager = DataManager()
            csv_df = data_manager.load_csv()
            
            # ========================================================
            # 2단계: 사용자 위치 정보
            # ========================================================
            user_lat = st.session_state.user_location['lat']
            user_lng = st.session_state.user_location['lng']
            
            # ========================================================
            # 3단계: 위치 기반 필터링 (반경 내 장소)
            # ========================================================
            filtered_csv = data_manager.filter_by_location(
                csv_df, user_lat, user_lng, radius_km
            )
            
            # ========================================================
            # 4단계: 카테고리 필터링
            # ========================================================
            filtered_csv = data_manager.filter_by_categories(
                filtered_csv, selected_categories
            )
            
            # ========================================================
            # 5단계: API 검색 (카카오 키가 있을 때만 실시간 보강)
            # ========================================================
            api_places = []
            kakao = None
            
            if st.session_state.get('kakao_api_key'):
                kakao = KakaoService(st.session_state.kakao_api_key)
                
                for category, code in DISPLAY_CATEGORIES.items():
                    if category in selected_categories:
                        results = kakao.search_places(
                            query="",
                            lat=user_lat,
                            lng=user_lng,
                            radius_km=radius_km,
                            category_code=code,
                            size=15
                        )
                        api_places.extend(results)
            
            # ========================================================
            # 6단계: CSV + API 데이터 통합
            # ========================================================
            all_places = data_manager.merge_with_api_data(
                filtered_csv,
                api_places
            )
            
            if all_places.empty:
                st.error(MESSAGES['no_results'])
            else:
                # ====================================================
                # 7단계: 추천 엔진 실행
                # ====================================================
                engine = RecommendationEngine(
                    data_manager,
                    kakao,
                    openai_api_key=st.session_state.get('openai_api_key', '')
                )
                
                # ====================================================
                # AI 사용 여부에 따라 다른 메서드 호출
                # ====================================================
                if use_ai and st.session_state.get('openai_api_key'):
                    st.info("🤖 AI가 최적의 여행 코스를 분석 중입니다...")
                    itinerary = engine.build_itinerary_with_ai(
                        all_places,
                        num_days,
                        user_lat,
                        user_lng,
                        selected_categories,
                        stay_name=st.session_state.user_location.get('name', '숙소'),
                        user_preferences=user_preferences
                    )
                else:
                    itinerary = engine.build_itinerary(
                        all_places,
                        num_days,
                        user_lat,
                        user_lng,
                        selected_categories,
                        stay_name=st.session_state.user_location.get('name', '숙소')
                    )
                
                # ====================================================
                # 8단계: 세션에 저장
                # ====================================================
                st.session_state.itinerary = itinerary
                st.session_state.all_places = all_places
                
                st.success(MESSAGES['search_success'].format(
                    count=len(all_places)
                ))
                st.rerun()


# ====================================================================
# 결과 표시
# ====================================================================

if st.session_state.itinerary:
    # ================================================================
    # 탭: 추천 일정, 전체 지도, 통계
    # ================================================================
    tabs = st.tabs(["📍 추천 일정", "🗺️ 전체 지도", "📊 통계"])
    
    # ================================================================
    # 탭 1: 추천 일정
    # ================================================================
    with tabs[0]:
        kakao = None
        if st.session_state.kakao_api_key:
            kakao = KakaoService(st.session_state.kakao_api_key)
        
        render_daily_itinerary(
            st.session_state.itinerary,
            st.session_state.all_places,
            DataManager(),
            kakao,
            st.session_state.user_location.get('name', '숙소')
        )
    
    # ================================================================
    # 탭 2: 전체 지도
    # ================================================================
    with tabs[1]:
        if st.session_state.user_location:
            render_full_map(
                st.session_state.itinerary,
                st.session_state.user_location['lat'],
                st.session_state.user_location['lng'],
                st.session_state.user_location['name']
            )
    
    # ================================================================
    # 탭 3: 통계
    # ================================================================
    with tabs[2]:
        render_statistics(st.session_state.itinerary)

else:
    # ================================================================
    # 초기 화면 (일정이 없을 때)
    # ================================================================
    st.info("""
    ### 🚀 시작하기
    
    1. **좌측 사이드바**에서 기준 위치를 검색하세요
    2. 여행 기간과 검색 반경을 설정하세요
    3. 관심 카테고리를 선택하세요
    4. **"추천 코스 생성"** 버튼을 클릭하세요!
    
    ---
    
    ### ✨ 주요 기능
    
    - ☕ **자연스러운 일정**: 모닝커피 → 관광 → 점심 → 오후활동 → 저녁 → 술집
    - 🤖 **AI 최적화**: ChatGPT가 동선과 선호도를 고려하여 추천 (OpenAI API 필요)
    - 🎯 **정확한 경로**: 카카오 네비게이션 API로 실제 거리/시간 계산
    - 📋 **상세 정보**: 운영시간, 평점, 리뷰, 사진까지 확인
    - 🗺️ **지도 표시**: 전체 동선을 한눈에
    - 🚗 **길찾기**: 카카오맵으로 바로 연결
    """)


# ====================================================================
# 푸터
# ====================================================================
st.divider()
st.caption("Made with ❤️ using Streamlit · 데이터 출처: 카카오맵 + CSV")
