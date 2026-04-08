# ============================================================
# app.py  |  제주 여행 맞춤 추천 v4.1  메인 앱
# ============================================================
# 실행: streamlit run app.py
#
# 전체 기능:
#   1. API 키 수동 입력 + 연결 상태 자동 확인
#   2. 숙소 검색 (🗺️ 카카오 API)
#   3. 여행 기간 / 카테고리 / 구조화된 AI 맞춤 조건 설정
#   4. 자동 추천 코스 생성
#   5. 결과: 일차별 탭 + 전체 지도 탭 + 코스 분석 탭
#   6. 우측 하단 플로팅 AI 챗봇 (OpenAI)
#
# 이번 수정 핵심:
#   - AI 맞춤 조건을 구조화 입력으로 변경
#   - 전역 / 음식 / 카페 / 관광 / 제외 조건 분리
#   - 추천 엔진에 preference_profile 형태로 전달
# ============================================================

import os
import datetime
from typing import Dict, List

import streamlit as st
from dotenv import load_dotenv

from config import PAGE_CONFIG, CATEGORIES
from data_manager import DataManager
from kakao_service import KakaoService
from recommendation_engine import RecommendationEngine
from ui_components import render_day_course, render_full_map, render_analysis
from chatbot import render_chatbot
from chroma_retriever import is_chroma_ready, get_similar_places

# .env 파일 읽기
load_dotenv()

# ── 페이지 설정 ─────────────────────────────────────────────
st.set_page_config(**PAGE_CONFIG)

# ── CSS ─────────────────────────────────────────────────────
st.markdown("""
<style>
div[data-testid="stAppViewContainer"] { background: #e0f2fe; }
section[data-testid="stMain"] { background: #e0f2fe; }
div[data-testid="stMainBlockContainer"] { background: #e0f2fe; }
.source-tip {
    font-size:12px; color:#64748b; border-left:3px solid #3b82f6;
    padding:4px 8px; margin:4px 0; background:#eff6ff; border-radius:4px;
}
.pref-box {
    background:#f8fafc;
    border:1px solid #cbd5e1;
    border-radius:8px;
    padding:10px 12px;
    margin:8px 0 12px 0;
}
.pref-title {
    font-weight:700;
    color:#0f172a;
    margin-bottom:4px;
}
.pref-desc {
    font-size:12px;
    color:#475569;
    margin-bottom:8px;
}
</style>
""", unsafe_allow_html=True)


# ── 세션 상태 초기화 ────────────────────────────────────────
def _init():
    defaults = dict(
        kakao_key=os.getenv("KAKAO_API_KEY"),
        openai_key=os.getenv("OPENAI_API_KEY"),
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


def _check_api():
    """앱 시작 시 .env 키로 연결 상태 자동 확인"""
    if not st.session_state.kakao_ok and st.session_state.kakao_key:
        ks = KakaoService(st.session_state.kakao_key)
        st.session_state.kakao_ok = ks.test_connection()

    if not st.session_state.openai_ok and st.session_state.openai_key:
        try:
            from openai import OpenAI
            OpenAI(api_key=st.session_state.openai_key).models.list()
            st.session_state.openai_ok = True
        except Exception:
            st.session_state.openai_ok = False


def _split_terms(text: str) -> List[str]:
    """
    쉼표/줄바꿈/슬래시 기준으로 입력을 나눠 리스트화
    """
    if not text or not text.strip():
        return []

    normalized = text.replace("\n", ",").replace("/", ",")
    parts = [p.strip() for p in normalized.split(",")]
    return [p for p in parts if p]


def _build_preference_profile(
    global_pref: str,
    food_pref: str,
    cafe_pref: str,
    tour_pref: str,
    negative_pref: str
) -> Dict[str, List[str]]:
    """
    구조화된 추천 조건 프로필 생성
    """
    return {
        "global_positive": _split_terms(global_pref),
        "food_positive": _split_terms(food_pref),
        "cafe_positive": _split_terms(cafe_pref),
        "tour_positive": _split_terms(tour_pref),
        "negative_terms": _split_terms(negative_pref),
    }


def _profile_to_text(profile: Dict[str, List[str]]) -> str:
    """
    분석 탭/챗봇에 넘길 요약 문자열
    """
    lines = []

    if profile.get("global_positive"):
        lines.append("전역 선호: " + ", ".join(profile["global_positive"]))
    if profile.get("food_positive"):
        lines.append("음식 선호: " + ", ".join(profile["food_positive"]))
    if profile.get("cafe_positive"):
        lines.append("카페 선호: " + ", ".join(profile["cafe_positive"]))
    if profile.get("tour_positive"):
        lines.append("관광 선호: " + ", ".join(profile["tour_positive"]))
    if profile.get("negative_terms"):
        lines.append("제외 조건: " + ", ".join(profile["negative_terms"]))

    return " | ".join(lines) if lines else ""


_init()
_check_api()


# ════════════════════════════════════════════════════════════
# 사이드바
# ════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🍊 제주 여행 추천 v4.1")
    st.caption("📊 CSV 데이터 + 🗺️ 카카오 API")
    st.divider()

    # ── 1. API 연결 상태 ────────────────────────────────────
    kakao_status = "✅ 연결됨" if st.session_state.kakao_ok else ("❌ 연결 실패" if st.session_state.kakao_key else "⚠️ 키 없음")
    openai_status = "✅ 연결됨" if st.session_state.openai_ok else ("❌ 연결 실패" if st.session_state.openai_key else "⚠️ 키 없음")
    st.caption(f"🔑 카카오 API: {kakao_status}")
    st.caption(f"🔑 OpenAI API: {openai_status}")

    st.divider()

    # ── 2. 숙소 검색 ────────────────────────────────────────
    st.markdown("### 🏨 숙소 / 출발지 설정")
    st.caption("🗺️ 카카오 API로 숙소명·브랜드명·주소를 실시간 검색합니다")

    accom_q = st.text_input(
        "숙소명 또는 주소 입력",
        placeholder="예: 그랜드 하얏트 제주, 제주 노연로 12, 제주특별자치도 제주시 ..."
    )

    if accom_q and st.session_state.kakao_ok:
        ks = KakaoService(st.session_state.kakao_key)
        results = ks.search_accommodation(accom_q)

        if results:
            options = [
                f"{r['place_name']}  ({r.get('road_address_name') or r.get('address_name','')})"
                f"{' [주소]' if r.get('category_name') == '주소 검색 결과' else ''}"
                for r in results
            ]
            sel_idx = st.selectbox(
                "🗺️ 카카오 검색 결과",
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
            st.warning("검색 결과 없음. 숙소명, 건물명, 도로명 주소, 지번 주소를 다시 확인해주세요.")
    elif accom_q and not st.session_state.kakao_ok:
        st.info("카카오 API 키를 먼저 입력하고 연결 확인을 해주세요.")

    st.caption(f"📍 현재 기준 위치: **{st.session_state.stay_name}**")
    st.divider()

    # ── 3. 여행 설정 ────────────────────────────────────────
    st.markdown("### ⚙️ 여행 설정")

    today = datetime.date.today()
    start_date = st.date_input("🗓️ 여행 시작일", value=today, min_value=today)
    end_date = st.date_input(
        "🗓️ 여행 종료일",
        value=today + datetime.timedelta(days=1),
        min_value=start_date
    )
    num_days = max(1, (end_date - start_date).days + 1)
    st.caption(f"총 {num_days}일 여행")

    if num_days > 7:
        st.warning("⚠️ 최대 7일까지 추천 가능합니다.")

    st.markdown("**📁 카테고리 선택**  *(📊 CSV 데이터 기준)*")
    all_sel = st.checkbox("전체 카테고리 선택", value=True, key="cat_all")
    if all_sel:
        sel_cats = CATEGORIES.copy()
        for c in CATEGORIES:
            st.checkbox(c, value=True, disabled=True, key=f"c_{c}")
    else:
        sel_cats = [c for c in CATEGORIES if st.checkbox(c, key=f"c_{c}")]

    st.markdown("**📍 추천 반경 설정**")
    radius_km = st.slider(
        "숙소 기준 반경 (km)",
        min_value=5,
        max_value=60,
        value=30,
        step=5,
        help="선택한 반경 내의 장소만 추천에 포함됩니다"
    )
    st.caption(f"📍 숙소에서 **{radius_km}km** 이내 장소만 추천")

    # ── 4. 구조화된 AI 맞춤 추천 조건 ───────────────────────
    st.markdown("### 🎯 AI 맞춤 추천 조건")

    st.markdown("""
<div class="pref-box">
  <div class="pref-title">전역 선호</div>
  <div class="pref-desc">전체 일정에 공통 적용됩니다. 예: 아이 동반, 조용한 곳, 웨이팅 적은 곳</div>
</div>
""", unsafe_allow_html=True)
    global_pref = st.text_area(
        "전역 선호",
        placeholder="예: 아이 동반, 조용한 곳, 웨이팅 적은 곳",
        height=70,
        label_visibility="collapsed",
    )

    st.markdown("""
<div class="pref-box">
  <div class="pref-title">음식 선호</div>
  <div class="pref-desc">점심/저녁 식사 슬롯에만 강하게 반영됩니다. 예: 흑돼지, 고기, 해산물</div>
</div>
""", unsafe_allow_html=True)
    food_pref = st.text_area(
        "음식 선호",
        placeholder="예: 흑돼지, 고기, 해산물",
        height=70,
        label_visibility="collapsed",
    )

    st.markdown("""
<div class="pref-box">
  <div class="pref-title">카페 선호</div>
  <div class="pref-desc">아침/오후 카페 슬롯에만 강하게 반영됩니다. 예: 바다뷰, 감성 카페, 디저트</div>
</div>
""", unsafe_allow_html=True)
    cafe_pref = st.text_area(
        "카페 선호",
        placeholder="예: 바다뷰, 감성 카페, 디저트",
        height=70,
        label_visibility="collapsed",
    )

    st.markdown("""
<div class="pref-box">
  <div class="pref-title">관광 선호</div>
  <div class="pref-desc">오전/오후 관광 슬롯에만 강하게 반영됩니다. 예: 오름, 산책, 실내 전시</div>
</div>
""", unsafe_allow_html=True)
    tour_pref = st.text_area(
        "관광 선호",
        placeholder="예: 오름, 산책, 실내 전시",
        height=70,
        label_visibility="collapsed",
    )

    st.markdown("""
<div class="pref-box">
  <div class="pref-title">제외 조건</div>
  <div class="pref-desc">해당 표현이 리뷰/키워드에 나타나면 감점합니다. 예: 웨이팅 긴 곳, 붐비는 곳, 매운 음식</div>
</div>
""", unsafe_allow_html=True)
    negative_pref = st.text_area(
        "제외 조건",
        placeholder="예: 웨이팅 긴 곳, 붐비는 곳, 매운 음식",
        height=70,
        label_visibility="collapsed",
    )

    preference_profile = _build_preference_profile(
        global_pref=global_pref,
        food_pref=food_pref,
        cafe_pref=cafe_pref,
        tour_pref=tour_pref,
        negative_pref=negative_pref,
    )
    preference_summary = _profile_to_text(preference_profile)

    if preference_summary:
        if is_chroma_ready():
            st.caption("입력하신 구조화 조건을 🧠 리뷰 유사도(Chroma) + 📊 CSV 키워드/리뷰에서 슬롯별로 반영합니다.")
        else:
            st.caption("입력하신 구조화 조건을 📊 CSV 키워드·리뷰에서 슬롯별로 반영합니다.")
            st.caption("💡 `python build_chroma.py` 실행 시 리뷰 유사도 검색이 함께 활성화됩니다")

    st.divider()

    # ── 5. 챗봇 토글 ────────────────────────────────────────
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
dm = DataManager()
stats = dm.stats()
cat_summary = "  ·  ".join([f"{k}: {v}개" for k, v in stats["by_cat"].items()])
st.success(f"📊 CSV 데이터 로딩 완료: 총 **{stats['total']}개** 장소  |  {cat_summary}")

st.divider()

# ── 추천 생성 버튼 ──────────────────────────────────────────
bc1, bc2 = st.columns([4, 1])
with bc1:
    gen_btn = st.button(
        "🚀 여행 코스 추천 생성",
        type="primary",
        use_container_width=True,
        disabled=(not sel_cats or num_days > 7),
    )

with bc2:
    if st.session_state.itinerary and st.button("🔄 초기화"):
        st.session_state.itinerary = []
        st.rerun()

if not sel_cats:
    st.warning("⚠️ 카테고리를 1개 이상 선택해주세요.")

# ── 추천 생성 ──────────────────────────────────────────────
if gen_btn and sel_cats:
    with st.spinner("✨ 추천 코스를 생성 중입니다... (📊 CSV 분석 중)"):
        kakao = KakaoService(st.session_state.kakao_key) if st.session_state.kakao_ok else None
        engine = RecommendationEngine(
            dm,
            kakao,
            st.session_state.openai_key if st.session_state.openai_ok else ""
        )

        ulat = st.session_state.user_lat
        ulng = st.session_state.user_lng

        # 슬롯별 Chroma 부스트
        chroma_boost = {
            "global": {},
            "food": {},
            "cafe": {},
            "tour": {},
        }

        if st.session_state.openai_ok and is_chroma_ready():
            try:
                with st.spinner("🧠 리뷰 유사도 분석 중..."):
                    if preference_profile["global_positive"]:
                        chroma_boost["global"] = get_similar_places(
                            " ".join(preference_profile["global_positive"]),
                            st.session_state.openai_key,
                        )

                    if preference_profile["food_positive"]:
                        chroma_boost["food"] = get_similar_places(
                            " ".join(preference_profile["food_positive"]),
                            st.session_state.openai_key,
                        )

                    if preference_profile["cafe_positive"]:
                        chroma_boost["cafe"] = get_similar_places(
                            " ".join(preference_profile["cafe_positive"]),
                            st.session_state.openai_key,
                        )

                    if preference_profile["tour_positive"]:
                        chroma_boost["tour"] = get_similar_places(
                            " ".join(preference_profile["tour_positive"]),
                            st.session_state.openai_key,
                        )
            except Exception:
                chroma_boost = {
                    "global": {},
                    "food": {},
                    "cafe": {},
                    "tour": {},
                }

        st.session_state.itinerary = engine.auto_recommend(
            num_days=num_days,
            cats=sel_cats,
            ulat=ulat,
            ulng=ulng,
            preferences=preference_summary,
            radius_km=radius_km,
            chroma_boost=chroma_boost,
            preference_profile=preference_profile,
        )

    st.success("✅ 추천 코스 생성 완료!")

# ── 결과 탭 ─────────────────────────────────────────────────
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
            st.caption("📊 장소 정보: CSV 데이터  ·  🗺️ 경로·지도: 카카오 API")
            render_day_course(
                day_info,
                st.session_state.user_lat,
                st.session_state.user_lng,
                kakao,
                stay_name=st.session_state.stay_name,
            )

    # 전체 지도 탭
    with all_tabs[num_days]:
        st.markdown("### 🗺️ 전체 일정 지도  *(일차별 색상 구분)*")
        st.caption("마커 위치: 📊 CSV 좌표 데이터  ·  지도 렌더링: Folium + 카카오 연동")
        render_full_map(
            itin,
            st.session_state.user_lat,
            st.session_state.user_lng,
            st.session_state.stay_name
        )

    # 코스 분석 탭
    with all_tabs[num_days + 1]:
        render_analysis(
            itin,
            sel_cats,
            preference_summary,
            num_days,
            "자동 추천 코스 생성"
        )

# ── AI 챗봇 패널 ────────────────────────────────────────────
if st.session_state.chat_open:
    st.divider()
    st.markdown("### 💬 AI 여행 챗봇  *(OpenAI API 사용)*")
    st.caption(
        "현재 추천 코스 관련 질문이나 제주 여행 정보를 자유롭게 질문하세요. "
        "📊 CSV 기반 추천 코스 컨텍스트를 AI가 참고합니다."
    )
    render_chatbot(st.session_state.itinerary, st.session_state.openai_key)