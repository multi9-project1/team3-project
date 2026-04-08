# ============================================================
# app.py  |  제주 여행 맞춤 추천 v4.2 (2차 버전: 리뷰 유사도 기반 추천)
# ============================================================
# 실행:
#   streamlit run app.py
#
# 전체 기능:
#   1. API 키 수동 입력 + 연결 상태 확인
#   2. 숙소 검색 (카카오 API)
#   3. 여행 기간 / 카테고리 / 사용자 요구 입력
#   4. 리뷰 유사도 기반 자동 추천 OR 직접 일정 구성
#   5. 결과: 일차별 탭 + 전체 지도 탭 + 코스 분석 탭
#   6. AI 챗봇
#
# 이번 버전 핵심:
#   - 추천 로직은 "리뷰 유사도 기반 추천" 전용
#   - 사용자 요구 문장과 각 장소 리뷰 문서의 의미적 유사도를 비교
# ============================================================

import streamlit as st
from datetime import datetime, timedelta

from config import PAGE_CONFIG, CATEGORIES, MANUAL_ACTIVITIES, MANUAL_TIMES
from data_manager import DataManager
from kakao_service import KakaoService
from recommendation_engine import RecommendationEngine
from ui_components import render_day_course, render_full_map, render_analysis
from chatbot import render_chatbot


# ------------------------------------------------------------
# 페이지 설정
# ------------------------------------------------------------
st.set_page_config(**PAGE_CONFIG)

# ------------------------------------------------------------
# CSS
# ------------------------------------------------------------
st.markdown("""
<style>
div[data-testid="stAppViewContainer"] { background: #111827; }
section[data-testid="stMain"] { background: #111827; }
div[data-testid="stMainBlockContainer"] { background: #111827; }
.source-tip {
    font-size: 12px;
    color: #64748b;
    border-left: 3px solid #3b82f6;
    padding: 4px 8px;
    margin: 4px 0;
    background: #eff6ff;
    border-radius: 4px;
}
</style>
""", unsafe_allow_html=True)


# ------------------------------------------------------------
# 세션 상태 초기화
# ------------------------------------------------------------
def _init():
    """앱 실행에 필요한 세션 상태 초기화"""
    defaults = dict(
        kakao_key="",
        openai_key="",
        kakao_ok=False,
        openai_ok=False,
        user_lat=33.4996213,
        user_lng=126.5311884,
        stay_name="제주시 (기본 출발지)",
        itinerary=[],
        chat_open=False,
    )
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init()


# ============================================================
# 사이드바
# ============================================================
with st.sidebar:
    st.markdown("## 🍊 제주 여행 추천 v4.2")
    st.caption("2차 버전: 🧠 리뷰 유사도 기반 추천")
    st.divider()

    # --------------------------------------------------------
    # 1. API 키 설정
    # --------------------------------------------------------
    st.markdown("### 🔑 API 키 설정")
    st.caption("입력 후 '연결 확인' 버튼을 눌러주세요.")

    with st.form("api_form"):
        k_in = st.text_input(
            "카카오 REST API 키",
            type="password",
            value=st.session_state.kakao_key
        )
        o_in = st.text_input(
            "OpenAI API 키 (선택)",
            type="password",
            value=st.session_state.openai_key
        )
        submitted = st.form_submit_button("🔗 연결 확인", use_container_width=True)

    if submitted:
        st.session_state.kakao_key = k_in
        st.session_state.openai_key = o_in

        ks = KakaoService(k_in)
        st.session_state.kakao_ok = ks.test_connection()

        if o_in:
            try:
                from openai import OpenAI
                OpenAI(api_key=o_in).models.list()
                st.session_state.openai_ok = True
            except Exception:
                st.session_state.openai_ok = False
        else:
            st.session_state.openai_ok = False

        st.rerun()

    if st.session_state.kakao_key:
        if st.session_state.kakao_ok:
            st.success("✅ 카카오 API 연결 완료")
        else:
            st.error("❌ 카카오 API 연결 실패")

    if st.session_state.openai_key:
        if st.session_state.openai_ok:
            st.success("✅ OpenAI API 연결 완료")
        else:
            st.error("❌ OpenAI API 연결 실패")

    st.divider()

    # --------------------------------------------------------
    # 2. 숙소 / 출발지 설정
    # --------------------------------------------------------
    st.markdown("### 🏨 숙소 / 출발지 설정")
    st.caption("카카오 API로 숙소명·브랜드명·주소를 검색합니다.")

    accom_q = st.text_input(
        "숙소명 또는 주소 입력",
        placeholder="예: 그랜드 하얏트 제주, 제주 노연로 12"
    )

    if accom_q and st.session_state.kakao_ok:
        ks = KakaoService(st.session_state.kakao_key)
        results = ks.search_accommodation(accom_q)

        if results:
            options = [
                f"{r['place_name']}  ({r.get('road_address_name') or r.get('address_name', '')})"
                f"{' [주소]' if r.get('category_name') == '주소 검색 결과' else ''}"
                for r in results
            ]

            sel_idx = st.selectbox(
                "카카오 검색 결과",
                range(len(options)),
                format_func=lambda i: options[i]
            )

            if st.button("✅ 이 숙소로 설정", use_container_width=True):
                r = results[sel_idx]
                st.session_state.user_lat = float(r["y"])
                st.session_state.user_lng = float(r["x"])
                st.session_state.stay_name = r["place_name"]
                st.success(f"📍 {r['place_name']} 선택 완료")
        else:
            st.warning("검색 결과가 없습니다. 숙소명 또는 주소를 다시 확인해주세요.")

    elif accom_q and not st.session_state.kakao_ok:
        st.info("카카오 API 키를 먼저 설정해주세요.")

    st.caption(f"📍 현재 기준 위치: **{st.session_state.stay_name}**")
    st.divider()

    # --------------------------------------------------------
    # 3. 여행 설정
    # --------------------------------------------------------
    st.markdown("### ⚙️ 여행 설정")

    start_date = st.date_input(
        "여행 시작일",
        value=datetime.today(),
        min_value=datetime.today(),
        max_value=datetime.today() + timedelta(days=7)
    )

    end_date = st.date_input(
        "여행 종료일",
        value=start_date + timedelta(days=1),
        min_value=start_date,
        max_value=datetime.today() + timedelta(days=7)
    )

    num_days = (end_date - start_date).days + 1

    if num_days > 7:
        st.warning("여행 기간은 최대 7일까지 설정 가능합니다.")

    st.markdown("**📁 카테고리 선택**")
    all_sel = st.checkbox("전체 카테고리 선택", value=True, key="cat_all")

    if all_sel:
        sel_cats = CATEGORIES.copy()
        for c in CATEGORIES:
            st.checkbox(c, value=True, disabled=True, key=f"c_{c}")
    else:
        sel_cats = [c for c in CATEGORIES if st.checkbox(c, key=f"c_{c}")]

    st.markdown("**🧠 리뷰 유사도 비교용 사용자 요구 입력**")
    preferences = st.text_area(
        "취향·조건 자유 입력 (선택)",
        placeholder="예: 조용하고 바다를 볼 수 있는 감성적인 카페, 사람이 너무 많지 않은 곳",
        height=95,
    )

    if preferences:
        st.caption("입력한 문장을 리뷰 의미와 비교하여 비슷한 장소를 추천합니다.")

    st.divider()

    # --------------------------------------------------------
    # 4. 추천 방식 선택
    # --------------------------------------------------------
    st.markdown("### 🎯 추천 방식")
    mode = st.radio(
        "방식 선택",
        ["자동 추천 코스 생성", "사용자 직접 일정 구성"],
        label_visibility="collapsed",
    )

    st.divider()

    # --------------------------------------------------------
    # 5. 챗봇 토글
    # --------------------------------------------------------
    chat_lbl = "💬 AI 챗봇 닫기 ✕" if st.session_state.chat_open else "💬 AI 챗봇 열기 ▲"
    if st.button(chat_lbl, use_container_width=True, type="secondary"):
        st.session_state.chat_open = not st.session_state.chat_open
        st.rerun()

    st.caption("OpenAI API 키가 있으면 추천 코스를 바탕으로 대화할 수 있습니다.")


# ============================================================
# 메인 화면
# ============================================================
st.title("🍊 제주 여행 맞춤 추천 시스템")
st.markdown(
    '<p class="source-tip">'
    '🧠 <b>현재 버전:</b> 리뷰 유사도 기반 추천 '
    '· 사용자 요구 문장과 장소 리뷰 문서의 의미적 유사도 비교 기반'
    '</p>',
    unsafe_allow_html=True,
)

st.markdown(
    '<p class="source-tip">'
    '📊 <b>CSV 데이터</b>: 팀 직접 수집한 제주 장소 정보 '
    '(장소명·주소·평점·리뷰·키워드) '
    ' | '
    '🗺️ <b>카카오 API</b>: 숙소 검색·네비경로·지도 링크'
    '</p>',
    unsafe_allow_html=True,
)

# ------------------------------------------------------------
# 데이터 로딩
# ------------------------------------------------------------
dm = DataManager()
stats = dm.stats()
cat_summary = "  ·  ".join([f"{k}: {v}개" for k, v in stats["by_cat"].items()])
st.success(f"📊 CSV 데이터 로딩 완료: 총 **{stats['total']}개** 장소 | {cat_summary}")

st.divider()

# ------------------------------------------------------------
# 직접 일정 구성 UI
# ------------------------------------------------------------
manual_schedule = []

if mode == "사용자 직접 일정 구성":
    st.markdown("### 📝 직접 일정 구성")
    st.caption("활동 유형과 시간대를 고르면 리뷰 유사도 기반으로 맞는 장소를 자동 매칭합니다.")

    for day in range(1, num_days + 1):
        st.markdown(f"**{day}일차**")
        cols = st.columns(3)

        for i in range(3):
            with cols[i]:
                act = st.selectbox(
                    f"활동 {i + 1}",
                    MANUAL_ACTIVITIES,
                    key=f"a{day}{i}"
                )
                tslot = st.selectbox(
                    "시간대",
                    MANUAL_TIMES,
                    key=f"t{day}{i}"
                )
                manual_schedule.append({
                    "day": day,
                    "activity": act,
                    "time_slot": tslot
                })

    st.divider()

# ------------------------------------------------------------
# 추천 생성 버튼
# ------------------------------------------------------------
bc1, bc2 = st.columns([4, 1])

with bc1:
    gen_btn = st.button(
        "🚀 리뷰 유사도 기반 여행 코스 생성",
        type="primary",
        use_container_width=True,
        disabled=(not sel_cats),
    )

with bc2:
    if st.session_state.itinerary and st.button("🔄 초기화"):
        st.session_state.itinerary = []
        st.rerun()

if not sel_cats:
    st.warning("⚠️ 카테고리를 1개 이상 선택해주세요.")

# ------------------------------------------------------------
# 추천 생성 실행
# ------------------------------------------------------------
if gen_btn and sel_cats:
    with st.spinner("✨ 리뷰 유사도 기반 추천 코스를 생성 중입니다... 모델 로드에 조금 시간이 걸릴 수 있어요."):
        kakao = KakaoService(st.session_state.kakao_key) if st.session_state.kakao_ok else None

        engine = RecommendationEngine(
            dm=dm,
            kakao=kakao,
            openai_key=st.session_state.openai_key if st.session_state.openai_ok else ""
        )

        ulat = st.session_state.user_lat
        ulng = st.session_state.user_lng

        if mode == "자동 추천 코스 생성":
            st.session_state.itinerary = engine.auto_recommend(
                num_days=num_days,
                cats=sel_cats,
                ulat=ulat,
                ulng=ulng,
                preferences=preferences
            )
        else:
            st.session_state.itinerary = engine.manual_recommend(
                schedule=manual_schedule,
                ulat=ulat,
                ulng=ulng,
                cats=sel_cats,
                preferences=preferences
            )

    st.success("✅ 리뷰 유사도 기반 추천 코스 생성 완료!")

# ------------------------------------------------------------
# 결과 출력
# ------------------------------------------------------------
if st.session_state.itinerary:
    itin = st.session_state.itinerary
    kakao = KakaoService(st.session_state.kakao_key) if st.session_state.kakao_ok else None

    day_tabs = [f"📅 {d}일차" for d in range(1, num_days + 1)]
    extra_tabs = ["🗺️ 전체 지도", "📊 코스 생성 분석"]
    all_tabs = st.tabs(day_tabs + extra_tabs)

    # 일차별 탭
    for i, day_info in enumerate(itin):
        with all_tabs[i]:
            st.markdown(f"## 📅 {day_info['day']}일차 여행 코스")
            st.caption("추천 기준: 리뷰 의미 유사도 + 평점 + 리뷰 수 + 거리")
            render_day_course(
                day_info,
                st.session_state.user_lat,
                st.session_state.user_lng,
                kakao,
            )

    # 전체 지도 탭
    with all_tabs[num_days]:
        st.markdown("### 🗺️ 전체 일정 지도")
        st.caption("일차별 색상으로 전체 이동 동선을 확인할 수 있습니다.")
        render_full_map(
            itin,
            st.session_state.user_lat,
            st.session_state.user_lng,
            st.session_state.stay_name
        )

    # 코스 분석 탭
    with all_tabs[num_days + 1]:
        render_analysis(
            itinerary=itin,
            cats=sel_cats,
            preferences=preferences,
            num_days=num_days,
            mode="리뷰 유사도 기반 추천"
        )

# ------------------------------------------------------------
# AI 챗봇 패널
# ------------------------------------------------------------
if st.session_state.chat_open:
    st.divider()
    st.markdown("### 💬 AI 여행 챗봇  *(OpenAI API + RAG 검색 사용)*")
    st.caption(
        "현재 추천 코스와 CSV 키워드/리뷰 기반 RAG 검색 결과를 함께 참고해 답변합니다."
    )
    render_chatbot(
        itinerary=st.session_state.itinerary,
        openai_key=st.session_state.openai_key,
        selected_categories=sel_cats,
        preferences=preferences,
        user_lat=st.session_state.user_lat,
        user_lng=st.session_state.user_lng,
        stay_name=st.session_state.stay_name,
    )
    