# ============================================================
# recommendation_engine.py  |  여행 코스 추천 엔진
# ============================================================
# 역할: CSV 데이터 기반 추천 로직 (두 가지 모드)
#   1. 자동 추천: 시간대별 슬롯에 맞는 장소 자동 배치
#   2. 직접 구성: 사용자 선택 활동 순서에 장소 매칭
#
# 점수 계산 기준 (📊 CSV 데이터):
#   - 평점(rating) * 10
#   - 리뷰 수(total_cnt) / 10 (최대 20점)
#   - 슬롯 키워드 매칭 +5점/개
#   - 사용자 선호 키워드 매칭 +10점/개 (reviews_text +3점)
#   - 거리 패널티 -0.5점/km
# ============================================================

import random
import pandas as pd
from typing import List, Dict, Optional
from config import TIME_SLOTS, CATEGORIES, OPENAI_MODEL
from data_manager import DataManager
from kakao_service import KakaoService, haversine

try:
    from openai import OpenAI
    OPENAI_OK = True
except ImportError:
    OPENAI_OK = False
    OpenAI = None


class RecommendationEngine:
    """여행 코스 추천 엔진  |  📊 CSV 데이터 기반"""

    def __init__(self, dm: DataManager,
                 kakao: Optional[KakaoService] = None,
                 openai_key: str = ""):
        self.dm = dm
        self.kakao = kakao
        # OpenAI 클라이언트 (선택적 활성화)
        self.ai = None
        if openai_key and OPENAI_OK:
            try:
                self.ai = OpenAI(api_key=openai_key)
            except Exception:
                pass

    # ── 자동 추천 ───────────────────────────────────────────
    def auto_recommend(self, num_days: int, cats: List[str],
                       ulat: float, ulng: float,
                       preferences: str = "") -> List[Dict]:
        """시간대별 자동 추천 코스 생성  |  📊 CSV 데이터"""
        df = self.dm.filter_by_cats(cats)
        used = set()   # 중복 방지: 이미 배치된 장소명 기록
        itinerary = []

        for day in range(1, num_days + 1):
            slots = []
            for slot in TIME_SLOTS:
                # 선택 안 된 카테고리는 유사 카테고리로 대체
                cat = slot["cat"] if slot["cat"] in cats else (cats[0] if cats else "기타")
                place = self._pick(df, cat, slot["kw"], ulat, ulng, used, preferences)
                if place:
                    used.add(place["name"])
                    pos_rv, neg_rv = self._classify_reviews(place.get("reviews_text", ""))
                    slots.append({
                        "slot":        slot,
                        "place":       place,
                        "reason":      self._reason(place, slot, preferences),
                        "pos_reviews": pos_rv,
                        "neg_reviews": neg_rv,
                    })
            itinerary.append({"day": day, "slots": slots})

        # OpenAI 사용 가능 시 추천 사유 보강
        if self.ai and preferences:
            itinerary = self._ai_enrich(itinerary, preferences)

        return itinerary

    # ── 직접 구성 ───────────────────────────────────────────
    def manual_recommend(self, schedule: List[Dict],
                         ulat: float, ulng: float,
                         cats: List[str], preferences: str = "") -> List[Dict]:
        """사용자 직접 구성 일정에 장소 매칭  |  📊 CSV 데이터"""
        df = self.dm.filter_by_cats(cats)
        used = set()
        days: Dict[int, list] = {}

        for item in schedule:
            day = item["day"]
            cat = self._activity_to_cat(item["activity"])
            slot = {"key": f"manual_{day}", "label": item["activity"],
                    "time": item["time_slot"], "cat": cat, "kw": []}
            place = self._pick(df, cat, [], ulat, ulng, used, preferences)
            if place:
                used.add(place["name"])
                days.setdefault(day, []).append({
                    "slot": slot, "place": place,
                    "reason": self._reason(place, slot, preferences),
                })

        return [{"day": d, "slots": s} for d, s in sorted(days.items())]

    # ── 내부: 장소 선택 ─────────────────────────────────────
    def _pick(self, df: pd.DataFrame, cat: str, kw: list,
              ulat: float, ulng: float, used: set,
              preferences: str) -> Optional[Dict]:
        """카테고리+키워드+거리+평점 종합 점수로 최적 장소 선택  |  📊 CSV"""
        pool = df[df["category"] == cat].copy()
        pool = pool[~pool["name"].isin(used)]
        # 해당 카테고리가 없으면 전체에서 선택
        if pool.empty:
            pool = df[~df["name"].isin(used)].copy()
        if pool.empty:
            return None

        pool = pool.copy()
        pool["_score"] = 0.0
        # 1. 평점 점수
        pool["_score"] += pool["rating"].fillna(3.5) * 10
        # 2. 리뷰 수 점수 (최대 20)
        pool["_score"] += pool["total_cnt"].fillna(0).clip(0, 200) / 10
        # 3. 슬롯 키워드 매칭 (📊 CSV keywords 컬럼)
        for w in kw:
            pool["_score"] += pool["keywords"].str.contains(w, na=False, case=False).astype(int) * 5
        # 4. 사용자 선호 조건 매칭 (📊 CSV keywords + reviews_text)
        if preferences:
            for w in preferences.split():
                pool["_score"] += pool["keywords"].str.contains(w, na=False, case=False).astype(int) * 10
                pool["_score"] += pool["reviews_text"].str.contains(w, na=False, case=False).astype(int) * 3
        # 5. 거리 패널티
        pool["_dist"] = pool.apply(
            lambda r: haversine(ulat, ulng, float(r["lat"]), float(r["lng"])), axis=1
        )
        pool["_score"] -= pool["_dist"].clip(0, 60) * 0.5

        # 상위 5개 중 무작위 1개 (다양성 확보)
        top5 = pool.nlargest(5, "_score")
        return top5.sample(1).iloc[0].to_dict()

    # ── 내부: 추천 이유 생성 ────────────────────────────────
    def _reason(self, place: Dict, slot: Dict, preferences: str) -> str:
        """추천 근거 문장 생성  |  📊 CSV 데이터 기반"""
        parts = []
        r = place.get("rating")
        if r and float(r) >= 4.5:
            parts.append(f"⭐ 평점 {r}")
        cnt = int(place.get("total_cnt", 0) or 0)
        if cnt >= 100:
            parts.append(f"💬 리뷰 {cnt}개")
        if preferences:
            for w in preferences.split()[:2]:
                kw_hit = w in str(place.get("keywords", ""))
                rv_hit = w in str(place.get("reviews_text", ""))
                if kw_hit or rv_hit:
                    parts.append(f"🎯 '{w}' 관련 언급 多")
                    break
        if not parts:
            parts.append(f"📍 {slot['label']} 시간대 추천 장소")
        return " · ".join(parts)

    # ── 내부: GPT 리뷰 긍정/부정 분류 ─────────────────────────
    # 키워드 기반 폴백용
    _POS_KW = ["좋아", "맛있", "최고", "추천", "훌륭", "깔끔", "친절", "만족", "완벽", "신선", "맛나", "감동", "좋았", "좋은", "맛집", "대박"]
    _NEG_KW = ["별로", "실망", "나쁘", "최악", "아쉽", "불친절", "비싸", "후회", "형편없", "안 좋", "별점 1", "별점1"]

    def _classify_reviews(self, reviews_text: str):
        """GPT로 리뷰 전체를 읽고 긍정/부정 요약문 생성. 실패 시 키워드 기반 폴백."""
        reviews = [
            r.strip() for r in str(reviews_text).split("|")
            if len(r.strip()) > 10 and r.strip().lower() != "nan"
        ]
        if not reviews:
            return [], []

        # GPT 요약 시도
        if self.ai:
            try:
                import random
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
                import json, re
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

        # 폴백: 키워드 기반 분류
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
        m = {"카페/디저트": "카페", "산책/자연": "자연",
             "관광/문화": "문화", "맛집": "맛집", "쇼핑/시장": "기타"}
        return m.get(activity, "기타")

    # ── OpenAI 추천 사유 보강 (선택) ─────────────────────────
    def _ai_enrich(self, itinerary: list, preferences: str) -> list:
        """OpenAI로 추천 사유 문장을 자연스럽게 보강 (코스 자체는 변경 안 함)"""
        try:
            for day_info in itinerary:
                for s in day_info["slots"][:2]:   # 과금 방지: 일차별 2개만
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
            pass   # AI 실패해도 기본 reason 유지
        return itinerary
