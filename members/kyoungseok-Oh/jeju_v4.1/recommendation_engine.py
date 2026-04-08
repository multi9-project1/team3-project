# ============================================================
# recommendation_engine.py  |  여행 코스 추천 엔진 (2차 버전: 리뷰 유사도 기반 추천)
# ============================================================
# 역할:
#   - CSV 리뷰 텍스트를 임베딩 벡터로 변환
#   - 사용자 입력 문장과 각 장소의 리뷰/키워드/이름/카테고리 문서를 비교
#   - 코사인 유사도를 바탕으로 장소를 추천
#
# 지원 모드:
#   1) 자동 추천: 시간대 슬롯에 맞는 장소 자동 배치
#   2) 직접 구성: 사용자가 고른 활동에 맞는 장소 매칭
#
# 점수 계산 기준:
#   - 리뷰/키워드 문서와 사용자 질의의 임베딩 유사도
#   - 슬롯 카테고리 보너스
#   - 평점 / 리뷰 수 보정
#   - 거리 패널티
#
# 참고:
#   - 이번 2차 버전은 리뷰 의미 유사도 기반 추천 전용
#   - 같은 문장이라도 표현이 조금 달라도 의미적으로 비슷하면 잡아낼 수 있음
# ============================================================

import json
import re
from typing import List, Dict, Optional

import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer

from config import TIME_SLOTS, OPENAI_MODEL
from data_manager import DataManager
from kakao_service import KakaoService, haversine

try:
    from openai import OpenAI
    OPENAI_OK = True
except ImportError:
    OPENAI_OK = False
    OpenAI = None


class RecommendationEngine:
    """여행 코스 추천 엔진 | 2차 버전: 리뷰 유사도 기반 추천"""

    def __init__(
        self,
        dm: DataManager,
        kakao: Optional[KakaoService] = None,
        openai_key: str = "",
        model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    ):
        self.dm = dm
        self.kakao = kakao

        # OpenAI는 추천 이유 문장 자연화용(선택)
        self.ai = None
        if openai_key and OPENAI_OK:
            try:
                self.ai = OpenAI(api_key=openai_key)
            except Exception:
                self.ai = None

        # 임베딩 모델 로드
        # 한국어/영어 혼합 텍스트에 비교적 안정적인 멀티링구얼 모델 사용
        self.model = SentenceTransformer(model_name)

        # 전체 데이터프레임 복사 후 임베딩용 문서 생성
        self.base_df = self.dm.df.copy()
        self.base_df["_doc_text"] = self.base_df.apply(self._make_doc_text, axis=1)

        # 전체 장소 문서 임베딩 미리 계산
        # normalize_embeddings=True 로 설정하면 코사인 유사도 계산이 안정적
        self.base_embeddings = self.model.encode(
            self.base_df["_doc_text"].tolist(),
            convert_to_numpy=True,
            normalize_embeddings=True
        )

    # --------------------------------------------------------
    # 자동 추천
    # --------------------------------------------------------
    def auto_recommend(
        self,
        num_days: int,
        cats: List[str],
        ulat: float,
        ulng: float,
        preferences: str = ""
    ) -> List[Dict]:
        """
        시간대 슬롯별로 리뷰 유사도 기반 자동 추천을 수행한다.
        """
        df = self.dm.filter_by_cats(cats)
        used = set()
        itinerary = []

        for day in range(1, num_days + 1):
            slots = []

            for slot in TIME_SLOTS:
                cat = slot["cat"] if slot["cat"] in cats else (cats[0] if cats else "기타")

                # 이번 2차 버전에서는
                # 사용자 선호 문장 + 슬롯 문맥을 합쳐서 질의 문장을 구성
                query_text = self._build_query_text(
                    preferences=preferences,
                    slot_keywords=slot.get("kw", []),
                    slot_label=slot.get("label", ""),
                    category=cat
                )

                place = self._pick(
                    df=df,
                    cat=cat,
                    query_text=query_text,
                    ulat=ulat,
                    ulng=ulng,
                    used=used,
                    preferences=preferences,
                    slot_keywords=slot.get("kw", [])
                )

                if place:
                    used.add(place["name"])
                    slots.append({
                        "slot": slot,
                        "place": place,
                        "reason": self._reason(place, slot, preferences)
                    })

            itinerary.append({
                "day": day,
                "slots": slots
            })

        if self.ai:
            itinerary = self._ai_enrich(itinerary, preferences)

        return itinerary

    # --------------------------------------------------------
    # 직접 구성 추천
    # --------------------------------------------------------
    def manual_recommend(
        self,
        schedule: List[Dict],
        ulat: float,
        ulng: float,
        cats: List[str],
        preferences: str = ""
    ) -> List[Dict]:
        """
        사용자가 직접 구성한 일정에 대해 리뷰 유사도 기반 추천 수행
        """
        df = self.dm.filter_by_cats(cats)
        used = set()
        days: Dict[int, list] = {}

        for idx, item in enumerate(schedule):
            day = item["day"]
            cat = self._activity_to_cat(item["activity"])

            slot = {
                "key": f"manual_{day}_{idx}",
                "label": item["activity"],
                "time": item["time_slot"],
                "cat": cat,
                "kw": []
            }

            query_text = self._build_query_text(
                preferences=preferences,
                slot_keywords=[],
                slot_label=item["activity"],
                category=cat
            )

            place = self._pick(
                df=df,
                cat=cat,
                query_text=query_text,
                ulat=ulat,
                ulng=ulng,
                used=used,
                preferences=preferences,
                slot_keywords=[]
            )

            if place:
                used.add(place["name"])
                days.setdefault(day, []).append({
                    "slot": slot,
                    "place": place,
                    "reason": self._reason(place, slot, preferences)
                })

        itinerary = [{"day": d, "slots": s} for d, s in sorted(days.items())]

        if self.ai:
            itinerary = self._ai_enrich(itinerary, preferences)

        return itinerary

    # --------------------------------------------------------
    # 내부: 장소별 문서 텍스트 생성
    # --------------------------------------------------------
    @staticmethod
    def _make_doc_text(row: pd.Series) -> str:
        """
        리뷰 유사도 비교용 장소 문서 생성
        리뷰만 쓰면 정보가 너무 좁을 수 있어
        이름/카테고리/키워드/리뷰를 함께 묶어서 사용한다.
        """
        return (
            f"장소명: {row.get('name', '')}\n"
            f"카테고리: {row.get('category', '')}\n"
            f"주소: {row.get('address', '')}\n"
            f"키워드: {row.get('keywords', '')}\n"
            f"리뷰: {row.get('reviews_text', '')}"
        )

    # --------------------------------------------------------
    # 내부: 사용자 질의 문장 구성
    # --------------------------------------------------------
    @staticmethod
    def _build_query_text(
        preferences: str,
        slot_keywords: List[str],
        slot_label: str,
        category: str
    ) -> str:
        """
        임베딩 비교용 질의 문장을 만든다.
        사용자 자유 입력 + 현재 슬롯 정보 + 카테고리를 함께 넣어
        해당 상황에 맞는 장소를 더 잘 찾게 한다.
        """
        parts = [
            f"일정 유형: {slot_label}",
            f"카테고리: {category}"
        ]

        if slot_keywords:
            parts.append(f"관련 키워드: {', '.join(slot_keywords)}")

        if preferences.strip():
            parts.append(f"사용자 선호 조건: {preferences.strip()}")

        return "\n".join(parts)

    # --------------------------------------------------------
    # 내부: 장소 선택 핵심 로직
    # --------------------------------------------------------
    def _pick(
        self,
        df: pd.DataFrame,
        cat: str,
        query_text: str,
        ulat: float,
        ulng: float,
        used: set,
        preferences: str,
        slot_keywords: List[str]
    ) -> Optional[Dict]:
        """
        리뷰 유사도 + 보정 점수로 최적 장소를 선택한다.
        """

        # 1) 선택 카테고리 후보 우선
        pool = df[df["category"] == cat].copy()
        pool = pool[~pool["name"].isin(used)]

        # 2) 비어 있으면 전체에서 재탐색
        if pool.empty:
            pool = df[~df["name"].isin(used)].copy()

        if pool.empty:
            return None

        # base_df와 인덱스를 맞추기 위해 현재 pool의 index를 사용
        candidate_idx = pool.index.to_list()

        # 질의 임베딩 생성
        query_embedding = self.model.encode(
            [query_text],
            convert_to_numpy=True,
            normalize_embeddings=True
        )

        # 후보군 임베딩만 추출
        candidate_embeddings = self.base_embeddings[candidate_idx]

        # 코사인 유사도 계산
        similarities = cosine_similarity(query_embedding, candidate_embeddings)[0]

        pool = pool.copy()
        pool["_similarity"] = similarities

        # 최종 점수 초기화
        pool["_score"] = 0.0

        # ----------------------------------------------------
        # 1. 리뷰 의미 유사도 (핵심)
        # ----------------------------------------------------
        pool["_score"] += pool["_similarity"] * 100

        # ----------------------------------------------------
        # 2. 카테고리 일치 보너스
        # ----------------------------------------------------
        pool["_score"] += (pool["category"] == cat).astype(int) * 8

        # ----------------------------------------------------
        # 3. 평점 보정
        # ----------------------------------------------------
        pool["_score"] += pool["rating"].fillna(3.5) * 4

        # ----------------------------------------------------
        # 4. 리뷰 수 보정
        # ----------------------------------------------------
        pool["_score"] += pool["total_cnt"].fillna(0).clip(0, 2000) / 40

        # ----------------------------------------------------
        # 5. 슬롯 키워드는 약한 보정으로만 사용
        # 2차 버전의 핵심은 유사도이므로 키워드 비중은 낮게
        # ----------------------------------------------------
        for w in slot_keywords:
            pool["_score"] += pool["keywords"].str.contains(w, na=False, case=False).astype(int) * 2
            pool["_score"] += pool["reviews_text"].str.contains(w, na=False, case=False).astype(int) * 1

        # ----------------------------------------------------
        # 6. 사용자 선호 키워드는 약한 보정으로 사용
        # 완전 배제하지 않고, 의미 검색을 보조하는 수준만 반영
        # ----------------------------------------------------
        user_terms = self._extract_terms(preferences)
        for w in user_terms:
            pool["_score"] += pool["keywords"].str.contains(w, na=False, case=False).astype(int) * 2
            pool["_score"] += pool["reviews_text"].str.contains(w, na=False, case=False).astype(int) * 1

        # ----------------------------------------------------
        # 7. 거리 패널티
        # ----------------------------------------------------
        pool["_dist"] = pool.apply(
            lambda r: haversine(
                ulat, ulng,
                float(r["lat"]),
                float(r["lng"])
            ),
            axis=1
        )

        pool["_score"] -= pool["_dist"].clip(0, 60) * 0.5

        # ----------------------------------------------------
        # 8. 비교 실험을 위해 랜덤 없이 1등만 선택
        # ----------------------------------------------------
        ranked = pool.sort_values("_score", ascending=False)
        return ranked.iloc[0].to_dict()

    # --------------------------------------------------------
    # 내부: 추천 이유 생성
    # --------------------------------------------------------
    def _reason(self, place: Dict, slot: Dict, preferences: str) -> str:
        """
        리뷰 유사도 기반 추천 이유 생성
        """
        pref_hits = self._matched_preferences(place, preferences)
        slot_hits = self._matched_slot_keywords(place, slot)
        label = self._plain_label(slot)

        if pref_hits:
            reason = (
                f"{', '.join(pref_hits)}와 관련된 리뷰 표현이 비슷하게 나타나 "
                f"{label} 일정에 잘 어울리는 장소예요."
            )
        elif slot_hits:
            reason = (
                f"{', '.join(slot_hits)}와 관련된 리뷰 맥락이 확인되어 "
                f"{label} 코스로 잘 맞는 장소예요."
            )
        else:
            reason = (
                f"사용자 요청과 리뷰 내용의 의미가 유사하게 나타나 "
                f"{label} 일정에 적합한 장소예요."
            )

        return self._trim_reason(reason)

    # --------------------------------------------------------
    # 내부: 이유 문자열 길이 정리
    # --------------------------------------------------------
    @staticmethod
    def _trim_reason(reason: str, limit: int = 100) -> str:
        cleaned = " ".join(str(reason or "").split())
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[: limit - 3].rstrip(" ,.;") + "..."

    # --------------------------------------------------------
    # 내부: 라벨 정리
    # --------------------------------------------------------
    @staticmethod
    def _plain_label(slot: Dict) -> str:
        label = str(slot.get("label", "이 일정"))
        cleaned = re.sub(r"[^0-9A-Za-z가-힣\s]", " ", label)
        return " ".join(cleaned.split()) or "이 일정"

    # --------------------------------------------------------
    # 내부: 비교용 단어 추출
    # --------------------------------------------------------
    @staticmethod
    def _extract_terms(text: str) -> List[str]:
        seen = []
        for term in re.findall(r"[0-9A-Za-z가-힣]{2,}", str(text or "")):
            if term not in seen:
                seen.append(term)
        return seen

    # --------------------------------------------------------
    # 내부: 사용자 선호 키워드 히트 확인
    # --------------------------------------------------------
    def _matched_preferences(self, place: Dict, preferences: str) -> List[str]:
        if not preferences:
            return []

        source = f"{place.get('keywords', '')} {place.get('reviews_text', '')}".lower()
        hits = []

        for term in self._extract_terms(preferences):
            if term.lower() in source and term not in hits:
                hits.append(term)
            if len(hits) == 2:
                break

        return hits

    # --------------------------------------------------------
    # 내부: 슬롯 키워드 히트 확인
    # --------------------------------------------------------
    def _matched_slot_keywords(self, place: Dict, slot: Dict) -> List[str]:
        source = f"{place.get('keywords', '')} {place.get('reviews_text', '')}".lower()
        hits = []

        for keyword in slot.get("kw", []):
            normalized = str(keyword).strip()
            if normalized and normalized.lower() in source and normalized not in hits:
                hits.append(normalized)
            if len(hits) == 2:
                break

        return hits

    # --------------------------------------------------------
    # 내부: AI 보강용 키워드 문맥
    # --------------------------------------------------------
    def _keyword_context(self, place: Dict, slot: Dict) -> List[str]:
        slot_hits = self._matched_slot_keywords(place, slot)
        if slot_hits:
            return slot_hits

        keywords = []
        for term in self._extract_terms(place.get("keywords", "")):
            keywords.append(term)
            if len(keywords) == 4:
                break
        return keywords

    # --------------------------------------------------------
    # 내부: 활동 -> 표준 카테고리 매핑
    # --------------------------------------------------------
    @staticmethod
    def _activity_to_cat(activity: str) -> str:
        mapping = {
            "카페/디저트": "카페",
            "산책/자연": "자연",
            "관광/문화": "문화",
            "맛집": "맛집",
            "쇼핑/시장": "기타",
        }
        return mapping.get(activity, "기타")

    # --------------------------------------------------------
    # 내부: OpenAI로 추천 이유 자연화
    # --------------------------------------------------------
    def _ai_enrich(self, itinerary: list, preferences: str) -> list:
        """
        코스 자체는 바꾸지 않고 추천 이유 문장만 자연스럽게 정리
        """
        if not self.ai or not itinerary:
            return itinerary

        try:
            slots = []
            for day_info in itinerary:
                for s in day_info.get("slots", []):
                    place = s["place"]
                    slots.append({
                        "day": day_info["day"],
                        "slot_key": s["slot"]["key"],
                        "slot_label": self._plain_label(s["slot"]),
                        "place_name": place.get("name", ""),
                        "category": place.get("category", ""),
                        "keyword_hints": self._keyword_context(place, s["slot"]),
                        "preference_hints": self._matched_preferences(place, preferences),
                        "fallback_reason": s["reason"],
                    })

            if not slots:
                return itinerary

            prompt = (
                "제주 여행 추천 앱의 추천 이유를 작성해줘.\n"
                "이번 추천은 리뷰 의미 유사도 기반 추천이다.\n"
                "규칙:\n"
                "1. 각 reason은 한국어 한 문장, 100자 이내\n"
                "2. 평점, 별점, 리뷰 수, 데이터 개수는 언급하지 말 것\n"
                "3. slot_label, category, keyword_hints, preference_hints를 바탕으로 설명할 것\n"
                "4. '리뷰 문맥이 비슷하다'는 성격이 자연스럽게 드러나게 할 것\n"
                "5. 과장된 광고 문구, 이모지, 따옴표는 쓰지 말 것\n"
                "6. JSON 배열만 반환할 것\n"
                "형식 예시: [{\"day\":1,\"slot_key\":\"morning_cafe\",\"reason\":\"...\"}]\n"
                f"항목: {json.dumps(slots, ensure_ascii=False)}"
            )

            res = self.ai.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "너는 제주 여행 추천 이유를 짧고 자연스럽게 쓰는 편집자다."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    },
                ],
                max_tokens=min(max(400, len(slots) * 70), 1800),
            )

            content = res.choices[0].message.content.strip()
            parsed = self._parse_ai_reasons(content)

            if not parsed:
                return itinerary

            for day_info in itinerary:
                for s in day_info.get("slots", []):
                    key = (day_info["day"], s["slot"]["key"])
                    if key in parsed:
                        s["reason"] = parsed[key]

        except Exception:
            pass

        return itinerary

    # --------------------------------------------------------
    # 내부: OpenAI 응답 파싱
    # --------------------------------------------------------
    def _parse_ai_reasons(self, content: str) -> Dict[tuple, str]:
        cleaned = str(content or "").strip()

        if cleaned.startswith("```"):
            cleaned = re.sub(
                r"^```(?:json)?\s*|\s*```$",
                "",
                cleaned,
                flags=re.DOTALL
            ).strip()

        start = cleaned.find("[")
        end = cleaned.rfind("]")

        if start == -1 or end == -1:
            return {}

        try:
            items = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            return {}

        parsed = {}
        for item in items:
            try:
                day = int(item.get("day"))
                slot_key = str(item.get("slot_key", "")).strip()
                reason = self._trim_reason(item.get("reason", ""))
            except Exception:
                continue

            if slot_key and reason:
                parsed[(day, slot_key)] = reason

        return parsed