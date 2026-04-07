# ============================================================
# chatbot.py  |  AI 여행 챗봇
# ============================================================
# 역할: OpenAI API를 활용한 제주 여행 전문 챗봇
#   - 현재 생성된 추천 코스를 컨텍스트로 전달
#   - 코스 관련 질문 및 일반 여행 질문 모두 답변
#   - 대화 이력 10턴 유지 (과금 방지)
#
# 출처: OpenAI API (gpt-4o-mini)  - 사용자 입력 키 사용
# ============================================================

import streamlit as st

try:
    from openai import OpenAI
    OPENAI_OK = True
except ImportError:
    OPENAI_OK = False


# ── 컨텍스트 빌더 ────────────────────────────────────────────
def _build_context(itinerary: list) -> str:
    """현재 추천 코스를 챗봇 시스템 프롬프트용 문자열로 변환"""
    if not itinerary:
        return "현재 생성된 추천 코스가 없습니다."
    lines = ["[현재 추천된 제주 여행 코스 (📊 CSV 데이터 기반)]"]
    for day in itinerary:
        lines.append(f"\n{day['day']}일차:")
        for s in day.get("slots", []):
            p = s.get("place", {})
            lines.append(
                f"  {s['slot']['label']}  →  {p.get('name','?')}"
                f"  ({p.get('address','')})"
                f"  | 이유: {s.get('reason','')}"
            )
    return "\n".join(lines)


# ── 챗봇 UI ─────────────────────────────────────────────────
def render_chatbot(itinerary: list, openai_key: str):
    """AI 챗봇 렌더링  |  OpenAI API"""

    if not openai_key or not OPENAI_OK:
        st.warning("💡 챗봇을 사용하려면 OpenAI API 키를 입력하고 연결을 확인해주세요.")
        return

    # 세션 대화 이력 / 입력창 키 초기화
    if "chat_msgs" not in st.session_state:
        st.session_state.chat_msgs = []
    if "chat_input_key" not in st.session_state:
        st.session_state.chat_input_key = 0

    # ── 대화 이력 표시 ──
    chat_box = st.container()
    with chat_box:
        for msg in st.session_state.chat_msgs:
            icon = "🧑" if msg["role"] == "user" else "🤖"
            align = "right" if msg["role"] == "user" else "left"
            bg    = "#dbeafe" if msg["role"] == "user" else "#f0fdf4"
            st.markdown(
                f'<div style="text-align:{align};margin:6px 0">'
                f'<span style="background:{bg};padding:8px 12px;border-radius:12px;display:inline-block;max-width:85%">'
                f'{icon} {msg["content"]}</span></div>',
                unsafe_allow_html=True
            )

    # ── 입력창 (키 카운터로 전송 후 자동 초기화) ──
    col_inp, col_btn = st.columns([5, 1])
    with col_inp:
        user_text = st.text_input(
            "chat_input", label_visibility="collapsed",
            placeholder="추천 코스나 제주 여행에 대해 질문해보세요!",
            key=f"chat_text_input_{st.session_state.chat_input_key}"
        )
    with col_btn:
        send = st.button("전송 ➤", use_container_width=True)

    col_clr, _ = st.columns([2, 5])
    with col_clr:
        if st.button("🗑️ 대화 초기화"):
            st.session_state.chat_msgs = []
            st.rerun()

    # ── 메시지 전송 처리 ──
    if send and user_text.strip():
        # 입력창 초기화: 키 카운터 증가 → 다음 렌더에서 빈 입력창으로 교체됨
        st.session_state.chat_input_key += 1
        st.session_state.chat_msgs.append(
            {"role": "user", "content": user_text.strip()}
        )

        system = f"""당신은 제주 여행 전문 AI 어시스턴트입니다.
아래 추천 코스 정보를 참고하여 사용자 질문에 친절하고 구체적으로 답변하세요.
한국어로 답변하며, 코스 이외 제주 여행 관련 질문도 성실히 답변해주세요.

{_build_context(itinerary)}"""

        # 최근 10턴만 포함 (토큰/비용 절감)
        recent = st.session_state.chat_msgs[-10:]

        reply = ""
        try:
            client = OpenAI(api_key=openai_key)
            # 스트리밍: 첫 토큰부터 즉시 표시해 체감 속도 개선
            stream = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": system}] + recent,
                max_completion_tokens=600,
                stream=True,
            )
            stream_box = st.empty()
            parts: list[str] = []
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    parts.append(delta)
                    stream_box.markdown(
                        f'<div style="text-align:left;margin:6px 0">'
                        f'<span style="background:#f0fdf4;padding:8px 12px;'
                        f'border-radius:12px;display:inline-block;max-width:85%">'
                        f'🤖 {"".join(parts)}▌</span></div>',
                        unsafe_allow_html=True,
                    )
            stream_box.empty()   # 스트리밍 임시 표시 제거 (rerun 후 정식 버블로 대체)
            reply = "".join(parts).strip()
        except Exception as e:
            reply = f"⚠️ 오류가 발생했습니다: {e}"

        st.session_state.chat_msgs.append(
            {"role": "assistant", "content": reply}
        )
        st.rerun()
