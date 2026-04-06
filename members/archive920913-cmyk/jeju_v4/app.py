# ============================================================
# app.py  |  제주 여행 맞춤 추천 v4.0  메인 앱
# ============================================================
# 실행: streamlit run app.py
#
# 전체 기능:
#   1. API 키 수동 입력 + 연결 상태 자동 확인
#   2. 숙소 검색 (🗺️ 카카오 API)
#   3. 여행 기간 / 카테고리 / AI 맞춤 조건 설정
#   4. 자동 추천 코스 생성 OR 사용자 직접 구성
#   5. 결과: 일차별 탭 + 전체 지도 탭 + 코스 분석 탭
#   6. 우측 하단 플로팅 AI 챗봇 (OpenAI)
# ============================================================

import streamlit as st
from config import PAGE_CONFIG, CATEGORIES, TRAVEL_DAYS, MANUAL_ACTIVITIES, MANUAL_TIMES
from data_manager import DataManager
from kakao_service import KakaoService
from recommendation_engine import RecommendationEngine
from ui_components import render_day_course, render_full_map, render_analysis
from chatbot import render_chatbot

# ── 페이지 설정 ─────────────────────────────────────────────
st.set_page_config(**PAGE_CONFIG)

# ── 플로팅 챗봇 버튼 CSS ────────────────────────────────────
st.markdown("""
<style>
div[data-testid="stAppViewContainer"] { background: #111827; }
section[data-testid="stMain"] { background: #111827; }
div[data-testid="stMainBlockContainer"] { background: #111827; }
.source-tip { font-size:12px; color:#64748b; border-left:3px solid #3b82f6;
              padding:4px 8px; margin:4px 0; background:#eff6ff; border-radius:4px; }
</style>
""", unsafe_allow_html=True)


# ── 세션 상태 초기화 ────────────────────────────────────────
def _init():
    defaults = dict(
        kakao_key="", openai_key="",
        kakao_ok=False, openai_ok=False,
        user_lat=33.4996213, user_lng=126.5311884,
        stay_name="제주시 (기본 출발지)",
        itinerary=[], chat_open=False,
    )
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init()


# ════════════════════════════════════════════════════════════
# 사이드바
# ════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🍊 제주 여행 추천 v4.0")
    st.caption("📊 CSV 데이터 + 🗺️ 카카오 API")
    st.divider()

    # ── 1. API 키 입력 ──────────────────────────────────────
    st.markdown("### 🔑 API 키 설정")
    st.caption("보안 입력창 — 입력 후 '연결 확인' 클릭")

    with st.form("api_form"):
        k_in = st.text_input("카카오 REST API 키", type="password",
                              value=st.session_state.kakao_key)
        o_in = st.text_input("OpenAI API 키 (챗봇/AI 추천용, 선택)", type="password",
                              value=st.session_state.openai_key)
        submitted = st.form_submit_button("🔗 연결 확인", use_container_width=True)

    if submitted:
        st.session_state.kakao_key  = k_in
        st.session_state.openai_key = o_in
        # 카카오 연결 테스트 (🗺️ 카카오 API)
        ks = KakaoService(k_in)
        st.session_state.kakao_ok = ks.test_connection()
        # OpenAI 연결 테스트
        if o_in:
            try:
                from openai import OpenAI
                OpenAI(api_key=o_in).models.list()
                st.session_state.openai_ok = True
            except Exception:
                st.session_state.openai_ok = False
        st.rerun()

    # API 상태 표시
    if st.session_state.kakao_key:
        if st.session_state.kakao_ok:
            st.success("✅ 카카오 API: 정상적으로 입력되었습니다.")
        else:
            st.error("❌ 카카오 API: 연결에 실패했습니다. API 키를 다시 확인해주세요.")
    if st.session_state.openai_key:
        if st.session_state.openai_ok:
            st.success("✅ OpenAI API: 정상적으로 입력되었습니다.")
        else:
            st.error("❌ OpenAI API: API 키를 다시 확인해주세요.")

    st.divider()

    # ── 2. 숙소 검색 (🗺️ 카카오 API) ──────────────────────
    st.markdown("### 🏨 숙소 / 출발지 설정")
    # 변경: 숙소명뿐 아니라 브랜드명·도로명 주소·지번 주소도 같은 입력창에서 검색할 수 있게 안내 문구를 확장한다.
    st.caption("🗺️ 카카오 API로 숙소명·브랜드명·주소를 실시간 검색합니다")
    accom_q = st.text_input(
        "숙소명 또는 주소 입력",
        placeholder="예: 그랜드 하얏트 제주, 제주 노연로 12, 제주특별자치도 제주시 ..."
    )

    if accom_q and st.session_state.kakao_ok:
        ks = KakaoService(st.session_state.kakao_key)
        results = ks.search_accommodation(accom_q)
        if results:
            # 변경: 주소 검색 결과도 섞여 들어오므로 선택 목록에서 결과 유형을 함께 보여준다.
            options = [
                f"{r['place_name']}  ({r.get('road_address_name') or r.get('address_name','')})"
                f"{' [주소]' if r.get('category_name') == '주소 검색 결과' else ''}"
                for r in results
            ]
            sel_idx = st.selectbox("🗺️ 카카오 검색 결과", range(len(options)),
                                   format_func=lambda i: options[i])
            if st.button("✅ 이 숙소로 설정", use_container_width=True):
                r = results[sel_idx]
                st.session_state.user_lat  = float(r["y"])
                st.session_state.user_lng  = float(r["x"])
                st.session_state.stay_name = r["place_name"]
                st.success(f"📍 {r['place_name']} 선택 완료")
        else:
            st.warning("검색 결과 없음. 숙소명, 건물명, 도로명 주소, 지번 주소를 다시 확인해주세요.")
    elif accom_q and not st.session_state.kakao_ok:
        st.info("카카오 API 키를 먼저 입력하고 연결 확인을 해주세요.")

    st.caption(f"📍 현재 기준 위치: **{st.session_state.stay_name}**")
    st.divider()

    # ── 3. 여행 설정 ────────────────────────────────────────
    st.markdown("### ⚙️ 여행 설정")
    travel_opt = st.selectbox("🗓️ 여행 기간", list(TRAVEL_DAYS.keys()))
    num_days   = TRAVEL_DAYS[travel_opt]

    st.markdown("**📁 카테고리 선택**  *(📊 CSV 데이터 기준)*")
    all_sel = st.checkbox("전체 카테고리 선택", value=True, key="cat_all")
    if all_sel:
        sel_cats = CATEGORIES.copy()
        for c in CATEGORIES:
            st.checkbox(c, value=True, disabled=True, key=f"c_{c}")
    else:
        sel_cats = [c for c in CATEGORIES if st.checkbox(c, key=f"c_{c}")]

    st.markdown("**🤖 AI 맞춤 추천 조건**")
    preferences = st.text_area(
        "취향·조건 자유 입력 (선택)",
        placeholder="예: 오징어 좋아함, 바다뷰 카페 선호, 아이 동반...",
        height=75,
    )
    if preferences:
        st.caption("입력하신 조건을 📊 CSV 키워드·리뷰에서 분석해 우선 반영합니다")

    st.divider()

    # ── 4. 추천 방식 선택 ───────────────────────────────────
    st.markdown("### 🎯 추천 방식")
    mode = st.radio(
        "방식 선택",
        ["자동 추천 코스 생성", "사용자 직접 일정 구성"],
        label_visibility="collapsed",
    )

    st.divider()

    # ── 5. 챗봇 토글 버튼 ───────────────────────────────────
    chat_lbl = "💬 AI 챗봇 닫기 ✕" if st.session_state.chat_open else "💬 AI 챗봇 열기 ▲"
    if st.button(chat_lbl, use_container_width=True, type="secondary"):
        st.session_state.chat_open = not st.session_state.chat_open
        st.rerun()
    st.caption("OpenAI API 키가 있으면 추천 코스 관련 대화 가능")


# ════════════════════════════════════════════════════════════
# 메인 화면
# ════════════════════════════════════════════════════════════
st.title("🍊 제주 여행 맞춤 추천 시스템")
st.markdown(
    '<p class="source-tip">📊 <b>CSV 데이터</b>: 팀 직접 수집한 제주 장소 정보 (장소명·주소·평점·리뷰·키워드)　|　'
    '🗺️ <b>카카오 API</b>: 숙소 검색·네비경로·지도 링크 (실시간)</p>',
    unsafe_allow_html=True,
)

# ── 데이터 로딩 & 통계 표시 ────────────────────────────────
dm    = DataManager()
stats = dm.stats()
cat_summary = "  ·  ".join([f"{k}: {v}개" for k, v in stats["by_cat"].items()])
st.success(f"📊 CSV 데이터 로딩 완료: 총 **{stats['total']}개** 장소  |  {cat_summary}")

st.divider()

# ── 직접 구성 UI ─────────────────────────────────────────────
manual_schedule = []
if mode == "사용자 직접 일정 구성":
    st.markdown("### 📝 직접 일정 구성  *(📊 CSV에서 장소 매칭)*")
    st.caption("활동 유형과 시간대를 선택하면 시스템이 CSV 데이터에서 맞는 장소를 자동 매칭합니다.")
    for day in range(1, num_days + 1):
        st.markdown(f"**{day}일차**")
        cols = st.columns(3)   # 하루 최대 3개 슬롯
        for i in range(3):
            with cols[i]:
                act  = st.selectbox(f"활동 {i+1}", MANUAL_ACTIVITIES, key=f"a{day}{i}")
                tslot = st.selectbox(f"시간대", MANUAL_TIMES, key=f"t{day}{i}")
                manual_schedule.append({"day": day, "activity": act, "time_slot": tslot})
    st.divider()

# ── 추천 생성 버튼 ──────────────────────────────────────────
bc1, bc2 = st.columns([4, 1])
with bc1:
    gen_btn = st.button(
        "🚀 여행 코스 추천 생성", type="primary",
        use_container_width=True,
        disabled=(not sel_cats),
    )
with bc2:
    if st.session_state.itinerary and st.button("🔄 초기화"):
        st.session_state.itinerary = []
        st.rerun()

if not sel_cats:
    st.warning("⚠️ 카테고리를 1개 이상 선택해주세요.")

if gen_btn and sel_cats:
    with st.spinner("✨ 추천 코스를 생성 중입니다... (📊 CSV 분석 중)"):
        kakao  = KakaoService(st.session_state.kakao_key) if st.session_state.kakao_ok else None
        engine = RecommendationEngine(
            dm, kakao,
            st.session_state.openai_key if st.session_state.openai_ok else ""
        )
        ulat = st.session_state.user_lat
        ulng = st.session_state.user_lng

        if mode == "자동 추천 코스 생성":
            st.session_state.itinerary = engine.auto_recommend(
                num_days, sel_cats, ulat, ulng, preferences
            )
        else:
            st.session_state.itinerary = engine.manual_recommend(
                manual_schedule, ulat, ulng, sel_cats, preferences
            )
    st.success("✅ 추천 코스 생성 완료!")

# ── 결과 탭 ─────────────────────────────────────────────────
if st.session_state.itinerary:
    itin  = st.session_state.itinerary
    kakao = KakaoService(st.session_state.kakao_key) if st.session_state.kakao_ok else None

    day_tabs   = [f"📅 {d}일차" for d in range(1, num_days + 1)]
    extra_tabs = ["🗺️ 전체 지도", "📊 코스 생성 분석"]
    all_tabs   = st.tabs(day_tabs + extra_tabs)

    # 일차별 탭
    for i, day_info in enumerate(itin):
        with all_tabs[i]:
            st.markdown(f"## 📅 {day_info['day']}일차 여행 코스")
            st.caption("📊 장소 정보: CSV 데이터  ·  🗺️ 경로·지도: 카카오 API")
            render_day_course(
                day_info,
                st.session_state.user_lat,
                st.session_state.user_lng,
                kakao,
            )

    # 전체 지도 탭
    with all_tabs[num_days]:
        st.markdown("### 🗺️ 전체 일정 지도  *(일차별 색상 구분)*")
        st.caption("마커 위치: 📊 CSV 좌표 데이터  ·  지도 렌더링: Folium + 카카오 연동")
        render_full_map(itin, st.session_state.user_lat,
                        st.session_state.user_lng, st.session_state.stay_name)

    # 코스 분석 탭
    with all_tabs[num_days + 1]:
        render_analysis(itin, sel_cats, preferences, num_days, mode)


# ── AI 챗봇 패널 (하단 표시) ────────────────────────────────
if st.session_state.chat_open:
    st.divider()
    st.markdown("### 💬 AI 여행 챗봇  *(OpenAI API 사용)*")
    st.caption(
        "현재 추천 코스 관련 질문이나 제주 여행 정보를 자유롭게 질문하세요. "
        "📊 CSV 기반 추천 코스 컨텍스트를 AI가 참고합니다."
    )
    render_chatbot(st.session_state.itinerary, st.session_state.openai_key)
