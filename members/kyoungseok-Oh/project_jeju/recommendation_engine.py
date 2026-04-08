# ============================================================
# recommendation_engine.py  |  여행 코스 추천 엔진
# ============================================================
# 역할: CSV 데이터 기반 추천 로직
#   1. 자동 추천: 시간대별 슬롯에 맞는 장소 자동 배치
#   2. 직접 구성: 사용자 선택 활동 순서에 장소 매칭
#
# 이번 수정 핵심:
#   - AI 맞춤 추천 조건을 구조화해서 슬롯별로 다르게 반영
#   - 전역 선호: 전체 슬롯
#   - 음식 선호: 점심/저녁
#   - 카페 선호: 아침/오후 카페
#   - 관광 선호: 오전/오후 관광
#   - 제외 조건: 감점
#   - Chroma 리뷰 유사도 부스트도 슬롯별로 다르게 반영
# ============================================================

import random
import re
from typing import List, Dict, Optional

import pandas as pd

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
    """여행 코스 추천 엔진 | 📊 CSV 데이터 기반"""

    def __init__(
        self,
        dm: DataManager,
        kakao: Optional[KakaoService] = None,
        openai_key: str = ""
    ):
        self.dm = dm
        self.kakao = kakao

        self.ai = None
        if openai_key and OPENAI_OK:
            try:
                self.ai = OpenAI(api_key=openai_key)
            except Exception:
                self.ai = None

    # ── 자동 추천 ───────────────────────────────────────────
    def auto_recommend(
        self,
        num_days: int,
        cats: List[str],
        ulat: float,
        ulng: float,
        preferences: str = "",
        radius_km: float = 30,
        chroma_boost: Optional[Dict] = None,
        preference_profile: Optional[Dict] = None,
    ) -> List[Dict]:
        """시간대별 자동 추천 코스 생성 | 구조화 취향 반영"""
        df = self.dm.filter_by_cats(cats)
        used = set()
        itinerary = []

        if chroma_boost is None:
            chroma_boost = {}
        if preference_profile is None:
            preference_profile = self._empty_profile()

        for day in range(1, num_days + 1):
            slots = []

            for slot in TIME_SLOTS:
                cat = slot["cat"] if slot["cat"] in cats else (cats[0] if cats else "기타")

                place = self._pick(
                    df=df,
                    cat=cat,
                    slot=slot,
                    ulat=ulat,
                    ulng=ulng,
                    used=used,
                    preferences=preferences,
                    radius_km=radius_km,
                    chroma_boost=chroma_boost,
                    preference_profile=preference_profile,
                )

                if place:
                    used.add(place["name"])
                    pos_rv, neg_rv = self._classify_reviews(place.get("reviews_text", ""))
                    slots.append({
                        "slot": slot,
                        "place": place,
                        "reason": self._reason(place, slot, preference_profile),
                        "pos_reviews": pos_rv,
                        "neg_reviews": neg_rv,
                    })

            itinerary.append({"day": day, "slots": slots})

        if self.ai and preferences:
            itinerary = self._ai_enrich(itinerary, preferences)

        return itinerary

    # ── 직접 구성 ───────────────────────────────────────────
    def manual_recommend(
        self,
        schedule: List[Dict],
        ulat: float,
        ulng: float,
        cats: List[str],
        preferences: str = "",
        preference_profile: Optional[Dict] = None,
    ) -> List[Dict]:
        """사용자 직접 구성 일정에 장소 매칭"""
        df = self.dm.filter_by_cats(cats)
        used = set()
        days: Dict[int, list] = {}

        if preference_profile is None:
            preference_profile = self._empty_profile()

        for item in schedule:
            day = item["day"]
            cat = self._activity_to_cat(item["activity"])

            slot = {
                "key": f"manual_{day}",
                "label": item["activity"],
                "time": item["time_slot"],
                "cat": cat,
                "kw": []
            }

            place = self._pick(
                df=df,
                cat=cat,
                slot=slot,
                ulat=ulat,
                ulng=ulng,
                used=used,
                preferences=preferences,
                radius_km=30,
                chroma_boost={},
                preference_profile=preference_profile,
            )

            if place:
                used.add(place["name"])
                days.setdefault(day, []).append({
                    "slot": slot,
                    "place": place,
                    "reason": self._reason(place, slot, preference_profile),
                })

        return [{"day": d, "slots": s} for d, s in sorted(days.items())]

    # ── 내부: 기본 프로필 ───────────────────────────────────
    @staticmethod
    def _empty_profile() -> Dict[str, List[str]]:
        return {
            "global_positive": [],
            "food_positive": [],
            "cafe_positive": [],
            "tour_positive": [],
            "negative_terms": [],
        }

    # ── 내부: 텍스트 정규화 ─────────────────────────────────
    @staticmethod
    def _normalize_terms(items: List[str]) -> List[str]:
        normalized = []
        for item in items or []:
            cleaned = str(item).strip()
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
        return normalized

    # ── 내부: 슬롯별 적용 선호 계산 ─────────────────────────
    def _get_slot_terms(self, slot: Dict, preference_profile: Dict) -> Dict[str, List[str]]:
        """
        슬롯 유형에 따라 적용할 선호 조건을 반환
        """
        profile = preference_profile or self._empty_profile()

        global_terms = self._normalize_terms(profile.get("global_positive", []))
        food_terms = self._normalize_terms(profile.get("food_positive", []))
        cafe_terms = self._normalize_terms(profile.get("cafe_positive", []))
        tour_terms = self._normalize_terms(profile.get("tour_positive", []))
        negative_terms = self._normalize_terms(profile.get("negative_terms", []))

        slot_key = str(slot.get("key", ""))
        slot_cat = str(slot.get("cat", ""))

        slot_terms = []
        slot_chroma_key = "global"

        if slot_cat == "맛집" or slot_key in ["lunch", "dinner"]:
            slot_terms = food_terms
            slot_chroma_key = "food"
        elif slot_cat == "카페" or slot_key in ["morning_cafe", "afternoon_cafe"]:
            slot_terms = cafe_terms
            slot_chroma_key = "cafe"
        elif slot_cat in ["자연", "문화"] or slot_key in ["morning_tour", "afternoon_tour"]:
            slot_terms = tour_terms
            slot_chroma_key = "tour"

        return {
            "global_terms": global_terms,
            "slot_terms": slot_terms,
            "negative_terms": negative_terms,
            "slot_chroma_key": slot_chroma_key,
        }

    # ── 내부: 점수화용 매칭 보조 ────────────────────────────
    @staticmethod
    def _contains_term(series: pd.Series, term: str) -> pd.Series:
        return series.str.contains(term, na=False, case=False)

    # ── 내부: 장소 선택 ─────────────────────────────────────
    def _pick(
        self,
        df: pd.DataFrame,
        cat: str,
        slot: Dict,
        ulat: float,
        ulng: float,
        used: set,
        preferences: str,
        radius_km: float = 30,
        chroma_boost: Optional[Dict] = None,
        preference_profile: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """카테고리+슬롯+구조화 취향+거리+평점 종합 점수로 최적 장소 선택"""
        if chroma_boost is None:
            chroma_boost = {}
        if preference_profile is None:
            preference_profile = self._empty_profile()

        pool = df[df["category"] == cat].copy()
        pool = pool[~pool["name"].isin(used)]

        if pool.empty:
            pool = df[~df["name"].isin(used)].copy()
        if pool.empty:
            return None

        pool = pool.copy()

        # 반경 필터
        pool["_dist"] = pool.apply(
            lambda r: haversine(ulat, ulng, float(r["lat"]), float(r["lng"])),
            axis=1
        )
        in_radius = pool[pool["_dist"] <= radius_km]
        if not in_radius.empty:
            pool = in_radius

        pool["_score"] = 0.0

        # 1) 기본 점수
        pool["_score"] += pool["rating"].fillna(3.5) * 10
        pool["_score"] += pool["total_cnt"].fillna(0).clip(0, 200) / 10

        # 2) 슬롯 키워드 반영
        for w in slot.get("kw", []):
            pool["_score"] += self._contains_term(pool["keywords"], w).astype(int) * 5
            pool["_score"] += self._contains_term(pool["reviews_text"], w).astype(int) * 2

        # 3) 구조화된 선호 반영
        slot_pref = self._get_slot_terms(slot, preference_profile)
        global_terms = slot_pref["global_terms"]
        slot_terms = slot_pref["slot_terms"]
        negative_terms = slot_pref["negative_terms"]
        slot_chroma_key = slot_pref["slot_chroma_key"]

        # 3-1) 전역 선호: 모든 슬롯 공통 반영
        for w in global_terms:
            pool["_score"] += self._contains_term(pool["keywords"], w).astype(int) * 8
            pool["_score"] += self._contains_term(pool["reviews_text"], w).astype(int) * 3

        # 3-2) 슬롯 선호: 해당 슬롯에서 강하게 반영
        # 음식/카페/관광 등
        for w in slot_terms:
            pool["_score"] += self._contains_term(pool["keywords"], w).astype(int) * 15
            pool["_score"] += self._contains_term(pool["reviews_text"], w).astype(int) * 5
            pool["_score"] += self._contains_term(pool["name"], w).astype(int) * 2

        # 3-3) 제외 조건: 감점
        for w in negative_terms:
            pool["_score"] -= self._contains_term(pool["keywords"], w).astype(int) * 10
            pool["_score"] -= self._contains_term(pool["reviews_text"], w).astype(int) * 4

        # 4) Chroma 리뷰 유사도 부스트
        # 전역 + 슬롯별 부스트를 합산
        if chroma_boost:
            global_boost = chroma_boost.get("global", {})
            specific_boost = chroma_boost.get(slot_chroma_key, {})

            if global_boost:
                pool["_score"] += pool["name"].map(global_boost).fillna(0)

            if specific_boost:
                pool["_score"] += pool["name"].map(specific_boost).fillna(0)

        # 5) 거리 패널티
        pool["_score"] -= pool["_dist"].clip(0, 60) * 0.5

        # 6) 상위 5개 중 무작위 1개
        top5 = pool.nlargest(5, "_score")
        return top5.sample(1).iloc[0].to_dict()

    # ── 내부: 추천 이유 생성 ────────────────────────────────
    def _reason(self, place: Dict, slot: Dict, preference_profile: Optional[Dict] = None) -> str:
        """추천 근거 문장 생성"""
        if preference_profile is None:
            preference_profile = self._empty_profile()

        parts = []

        rating = place.get("rating")
        if rating and float(rating) >= 4.5:
            parts.append(f"⭐ 평점 {rating}")

        cnt = int(place.get("total_cnt", 0) or 0)
        if cnt >= 100:
            parts.append(f"💬 리뷰 {cnt}개")

        slot_pref = self._get_slot_terms(slot, preference_profile)
        candidate_terms = slot_pref["slot_terms"] + slot_pref["global_terms"]

        text = f"{place.get('keywords', '')} {place.get('reviews_text', '')}"

        for w in candidate_terms[:4]:
            if w and w.lower() in str(text).lower():
                parts.append(f"🎯 '{w}' 조건 반영")
                break

        if not parts:
            parts.append(f"📍 {slot['label']} 시간대 추천 장소")

        return " · ".join(parts)

    # ── 내부: GPT 리뷰 긍정/부정 분류 ─────────────────────────
    _POS_KW = ["좋아", "맛있", "최고", "추천", "훌륭", "깔끔", "친절", "만족", "완벽", "신선", "맛나", "감동", "좋았", "좋은", "맛집", "대박"]
    _NEG_KW = ["별로", "실망", "나쁘", "최악", "아쉽", "불친절", "비싸", "후회", "형편없", "안 좋", "별점 1", "별점1", "웨이팅", "붐빔"]

    def _classify_reviews(self, reviews_text: str):
        """GPT로 리뷰 전체를 읽고 긍정/부정 요약문 생성. 실패 시 키워드 기반 폴백."""
        reviews = [
            r.strip() for r in str(reviews_text).split("|")
            if len(r.strip()) > 10 and r.strip().lower() != "nan"
        ]
        if not reviews:
            return [], []

        if self.ai:
            try:
                sample = random.sample(reviews, min(20, len(reviews)))
                all_reviews = " / ".join(sample)
                prompt = (
                    f"다음은 한국어 장소 리뷰들이야:\n{all_reviews}\n\n"
                    f"이 리뷰들을 읽고 긍정적인 내용을 한 문장으로, 부정적인 내용을 한 문장으로 요약해줘.\n"
                    f"부정적인 내용이 없으면 neg는 빈 문자열로.\n"
                    f"코드블록 없이 JSON만 반환: {{\"pos\": \"요약\", \"neg\": \"요약\"}}"
                )
                res = self.ai.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_completion_tokens=200,
                )

                import json
                content = res.choices[0].message.content
                if not content:
                    raise ValueError("empty response from model")

                raw = re.sub(r"```(?:json)?\s*|\s*```", "", content.strip()).strip()
                data = json.loads(raw)

                pos_summary = data.get("pos", "").strip()
                neg_summary = data.get("neg", "").strip()
                return ([pos_summary] if pos_summary else []), ([neg_summary] if neg_summary else [])

            except Exception as e:
                print(f"[리뷰 분류 GPT 오류] {e}")

        # 폴백
        pos, neg = [], []
        for rv in reviews:
            is_neg = any(w in rv for w in self._NEG_KW)
            is_pos = any(w in rv for w in self._POS_KW)
            if is_neg and not is_pos:
                neg.append(rv)
            else:
                pos.append(rv)

        return pos[:3], neg[:3]

    # ── 내부: 활동 → 카테고리 변환 ─────────────────────────
    @staticmethod
    def _activity_to_cat(activity: str) -> str:
        mapping = {
            "카페/디저트": "카페",
            "산책/자연": "자연",
            "관광/문화": "문화",
            "맛집": "맛집",
            "쇼핑/시장": "기타"
        }
        return mapping.get(activity, "기타")

    # ── OpenAI 추천 사유 보강 (선택) ─────────────────────────
    def _ai_enrich(self, itinerary: list, preferences: str) -> list:
        """OpenAI로 추천 사유 문장을 자연스럽게 보강 (코스 자체는 변경 안 함)"""
        try:
            for day_info in itinerary:
                for s in day_info["slots"][:2]:
                    p = s["place"]
                    prompt = (
                        f"제주 여행 추천 앱. 사용자 선호: '{preferences}'. "
                        f"추천 장소: {p.get('name')} ({p.get('category')}). "
                        f"키워드: {p.get('keywords','')[:80]}. "
                        f"왜 이 장소가 잘 맞는지 한 문장(20자 내)으로 설명해줘."
                    )
                    res = self.ai.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                        max_completion_tokens=60,
                    )
                    ai_reason = res.choices[0].message.content.strip()
                    s["reason"] = f"🤖 {ai_reason}"
        except Exception:
            pass

        return itinerary