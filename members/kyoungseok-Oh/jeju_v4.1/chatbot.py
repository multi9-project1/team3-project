# ============================================================
# chatbot.py  |  AI 여행 챗봇 + RAG 검색
# ============================================================
# 역할:
#   - 현재 생성된 추천 코스를 컨텍스트로 전달
#   - 추가로 CSV keywords/reviews_text 기반 RAG 검색 수행
#   - 사용자가 입력한 문장에서 핵심어를 추출하고
#     retriever.as_retriever(search_kwargs={"k": 10}) 로 top-k 검색
#   - 검색 결과 + 현재 코스 정보를 함께 OpenAI에 전달
#
# 주의:
#   - 첫 번째 화면의 코스 생성 로직은 건드리지 않음
#   - 이 파일은 "하단 챗봇" 부분만 강화하는 용도
# ============================================================

import re
from typing import List, Dict, Optional

import streamlit as st

try:
    from openai import OpenAI
    OPENAI_OK = True
except ImportError:
    OPENAI_OK = False
    OpenAI = None
from typing import List, Optional, Tuple
# RAG용 패키지
try:
    from langchain_core.documents import Document
    from langchain_community.vectorstores import FAISS
    from langchain_huggingface import HuggingFaceEmbeddings
    LANGCHAIN_OK = True
except ImportError:
    LANGCHAIN_OK = False
    Document = None
    FAISS = None
    HuggingFaceEmbeddings = None

from data_manager import DataManager
from kakao_service import haversine


# ------------------------------------------------------------
# 현재 추천 코스 컨텍스트
# ------------------------------------------------------------
def _build_itinerary_context(itinerary: list) -> str:
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
                f"  | 카테고리: {p.get('category','')}"
                f"  | 이유: {s.get('reason','')}"
            )
    return "\n".join(lines)


# ------------------------------------------------------------
# 핵심어 추출
# ------------------------------------------------------------
def _extract_terms(text: str) -> List[str]:
    """
    사용자 문장에서 비교용 핵심 단어 추출
    예:
        "나는 고기를 좋아해서 흑돼지 맛집을 가고 싶어"
        -> ["고기", "흑돼지", "맛집"]
    """
    tokens = re.findall(r"[0-9A-Za-z가-힣]{2,}", str(text or "").lower())

    stopwords = {
        "나는", "저는", "제가", "우리", "너무", "정말", "그냥",
        "좋아", "좋아해", "좋아해서", "싶어", "싶어요", "가고",
        "가고싶어", "가고싶어요", "추천", "추천해줘", "추천해주세요",
        "장소", "곳", "여행", "제주", "근처", "관련", "대해", "현재",
        "코스", "일정", "말해줘", "알려줘", "해주세요", "합니다"
    }

    seen = []
    for token in tokens:
        if token in stopwords:
            continue
        if token not in seen:
            seen.append(token)

    return seen


# ------------------------------------------------------------
# RAG용 장소 문서 생성
# ------------------------------------------------------------
def _make_place_document(row) -> str:
    """
    retriever가 검색할 문서 본문
    keywords + reviews_text + 이름/카테고리/주소를 함께 포함
    """
    return (
        f"장소명: {row.get('name', '')}\n"
        f"카테고리: {row.get('category', '')}\n"
        f"주소: {row.get('address', '')}\n"
        f"키워드: {row.get('keywords', '')}\n"
        f"리뷰: {row.get('reviews_text', '')}\n"
    )


# ------------------------------------------------------------
# RAG 리소스 생성
# ------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def _build_rag_resources():
    """
    CSV 전체를 읽어 벡터스토어를 1회만 생성
    첫 번째 화면 코스 생성과는 별개로, 챗봇에서만 사용
    """
    if not LANGCHAIN_OK:
        return None, None, None

    dm = DataManager()
    df = dm.df.copy()

    docs = []
    for _, row in df.iterrows():
        metadata = {
            "name": row.get("name", ""),
            "category": row.get("category", ""),
            "address": row.get("address", ""),
            "lat": float(row.get("lat", 0) or 0),
            "lng": float(row.get("lng", 0) or 0),
            "rating": float(row.get("rating", 0) or 0),
            "total_cnt": int(row.get("total_cnt", 0) or 0),
            "keywords": str(row.get("keywords", "")),
            "reviews_text": str(row.get("reviews_text", "")),
            "place_url": str(row.get("place_url", "")),
        }
        docs.append(
            Document(
                page_content=_make_place_document(row),
                metadata=metadata
            )
        )

    if not docs:
        return dm, df, None

    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True}
    )

    vectorstore = FAISS.from_documents(docs, embeddings)
    return dm, df, vectorstore


# ------------------------------------------------------------
# retriever 질의 생성
# ------------------------------------------------------------
def _build_rag_query(
    user_text: str,
    selected_categories: Optional[List[str]] = None,
    preferences: str = ""
) -> (str, List[str]):
    core_terms = _extract_terms(user_text)

    parts = []
    if selected_categories:
        parts.append("카테고리: " + ", ".join(selected_categories))
    if preferences.strip():
        parts.append("현재 추천 조건: " + preferences.strip())
    if core_terms:
        parts.append("핵심어: " + ", ".join(core_terms))
    parts.append("원문 질문: " + user_text.strip())

    return "\n".join(parts), core_terms


# ------------------------------------------------------------
# retriever 검색
# ------------------------------------------------------------
def _retrieve_places(
    user_text: str,
    selected_categories: Optional[List[str]] = None,
    preferences: str = "",
    user_lat: Optional[float] = None,
    user_lng: Optional[float] = None,
    k: int = 10
) -> List[Dict]:
    """
    CSV keywords/reviews_text 기반 RAG 검색
    핵심:
        retriever.as_retriever(search_kwargs={"k": 10})
    """
    if not LANGCHAIN_OK:
        return []

    dm, df, vectorstore = _build_rag_resources()
    if vectorstore is None:
        return []

    query_text, core_terms = _build_rag_query(
        user_text=user_text,
        selected_categories=selected_categories,
        preferences=preferences
    )

    retriever = vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={"k": k}
    )

    docs = retriever.invoke(query_text)

    results = []
    seen_names = set()

    for rank, doc in enumerate(docs, start=1):
        meta = doc.metadata
        name = meta.get("name", "")

        # 카테고리 후처리 필터
        if selected_categories and meta.get("category") not in selected_categories:
            continue

        # 중복 제거
        if name in seen_names:
            continue
        seen_names.add(name)

        # 거리 계산
        distance_km = None
        if user_lat is not None and user_lng is not None:
            try:
                distance_km = haversine(
                    float(user_lat),
                    float(user_lng),
                    float(meta.get("lat", 0)),
                    float(meta.get("lng", 0)),
                )
            except Exception:
                distance_km = None

        # 추천 이유 생성
        source_text = f"{meta.get('keywords', '')} {meta.get('reviews_text', '')}".lower()
        hits = []
        for term in core_terms:
            if term.lower() in source_text and term not in hits:
                hits.append(term)
            if len(hits) >= 3:
                break

        if hits:
            reason = f"질문의 핵심어인 {', '.join(hits)} 와 관련된 키워드/리뷰 문맥이 유사해 검색된 장소예요."
        else:
            reason = "질문 문장과 키워드·리뷰 문맥의 의미 유사도가 높아 검색된 장소예요."

        results.append({
            "rank": rank,
            "name": meta.get("name", ""),
            "category": meta.get("category", ""),
            "address": meta.get("address", ""),
            "rating": meta.get("rating", 0),
            "total_cnt": meta.get("total_cnt", 0),
            "keywords": meta.get("keywords", ""),
            "reviews_text": meta.get("reviews_text", ""),
            "place_url": meta.get("place_url", ""),
            "lat": meta.get("lat", 0),
            "lng": meta.get("lng", 0),
            "distance_km": distance_km,
            "reason": reason,
            "retrieved_text": doc.page_content,
        })

    # 너무 멀면 뒤로 보내는 약한 정렬
    def _sort_key(item):
        dist = item["distance_km"]
        return (999999 if dist is None else dist)

    if user_lat is not None and user_lng is not None:
        results = sorted(results, key=_sort_key)

    return results[:k]


# ------------------------------------------------------------
# RAG 검색 결과를 프롬프트용 텍스트로 변환
# ------------------------------------------------------------
def _build_rag_context(results: List[Dict]) -> str:
    if not results:
        return "RAG 검색 결과가 없습니다."

    lines = ["[CSV 키워드/리뷰 기반 RAG 검색 결과 top-k]"]
    for idx, item in enumerate(results, start=1):
        lines.append(
            f"\n{idx}. {item['name']}"
            f"\n- 카테고리: {item['category']}"
            f"\n- 주소: {item['address']}"
            f"\n- 평점: {item['rating']}"
            f"\n- 리뷰 수: {item['total_cnt']}"
            f"\n- 키워드: {item['keywords']}"
            f"\n- 추천 이유: {item['reason']}"
            f"\n- 리뷰 일부: {str(item['reviews_text'])[:220]}"
        )
    return "\n".join(lines)


# ------------------------------------------------------------
# 챗봇 UI
# ------------------------------------------------------------
def render_chatbot(
    itinerary: list,
    openai_key: str,
    selected_categories: Optional[List[str]] = None,
    preferences: str = "",
    user_lat: Optional[float] = None,
    user_lng: Optional[float] = None,
    stay_name: str = ""
):
    """AI 챗봇 렌더링 | OpenAI + RAG"""

    if not openai_key or not OPENAI_OK:
        st.warning("💡 챗봇을 사용하려면 OpenAI API 키를 입력하고 연결을 확인해주세요.")
        return

    if "chat_msgs" not in st.session_state:
        st.session_state.chat_msgs = []

    # 대화 이력 표시
    chat_box = st.container()
    with chat_box:
        for msg in st.session_state.chat_msgs:
            icon = "🧑" if msg["role"] == "user" else "🤖"
            align = "right" if msg["role"] == "user" else "left"
            bg = "#dbeafe" if msg["role"] == "user" else "#f0fdf4"
            st.markdown(
                f'<div style="text-align:{align};margin:6px 0">'
                f'<span style="background:{bg};color:#111827;padding:8px 12px;border-radius:12px;display:inline-block;max-width:85%">'
                f'{icon} {msg["content"]}</span></div>',
                unsafe_allow_html=True
            )

    # 입력창
    col_inp, col_btn = st.columns([5, 1])
    with col_inp:
        user_text = st.text_input(
            "chat_input",
            label_visibility="collapsed",
            placeholder="추천 코스나 제주 여행에 대해 질문해보세요!",
            key="chat_text_input"
        )
    with col_btn:
        send = st.button("전송 ➤", use_container_width=True)

    col_clr, _ = st.columns([2, 5])
    with col_clr:
        if st.button("🗑️ 대화 초기화"):
            st.session_state.chat_msgs = []
            st.rerun()

    # 메시지 전송 처리
    if send and user_text.strip():
        clean_text = user_text.strip()
        st.session_state.chat_msgs.append({"role": "user", "content": clean_text})

        # RAG 검색
        rag_results = _retrieve_places(
            user_text=clean_text,
            selected_categories=selected_categories,
            preferences=preferences,
            user_lat=user_lat,
            user_lng=user_lng,
            k=10
        )
        rag_context = _build_rag_context(rag_results)

        # 검색 결과 미리보기 (사용자 확인용)
        if rag_results:
            with st.expander("🔎 챗봇이 참고한 RAG 검색 결과 top 10", expanded=False):
                for idx, item in enumerate(rag_results, start=1):
                    st.markdown(
                        f"**{idx}. {item['name']}**  "
                        f"({item['category']})  \n"
                        f"- 주소: {item['address']}  \n"
                        f"- 추천 이유: {item['reason']}"
                    )

        system = f"""당신은 제주 여행 전문 AI 어시스턴트입니다.
아래 두 가지 정보를 함께 참고하여 사용자 질문에 친절하고 구체적으로 답변하세요.

1) 현재 생성된 추천 코스
2) CSV의 keywords/reviews_text 기반 RAG 검색 결과 top 10

답변 규칙:
- 한국어로만 답변할 것
- 현재 추천 코스가 있으면 먼저 그 코스와 연결해서 설명할 것
- 추가 추천이 필요하면 RAG 검색 결과 안에서만 제안할 것
- 없는 정보를 지어내지 말 것
- 사용자가 특정 음식/분위기/장소를 말하면, 그 핵심어와 관련된 장소를 우선 설명할 것
- 제주도 여행과 관련 없는 질문이 나오면 "제주 여행과 관련된 질문을 해주세요"라고 답할 것

[현재 출발지]
{stay_name}

[현재 선택 카테고리]
{", ".join(selected_categories or [])}

[현재 추천 조건]
{preferences}

{_build_itinerary_context(itinerary)}

{rag_context}
"""

        recent = st.session_state.chat_msgs[-10:]

        try:
            client = OpenAI(api_key=openai_key)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": system}] + recent,
                max_tokens=700,
            )
            reply = resp.choices[0].message.content.strip()
        except Exception as e:
            reply = f"⚠️ 오류가 발생했습니다: {e}"

        st.session_state.chat_msgs.append({"role": "assistant", "content": reply})
        st.rerun()