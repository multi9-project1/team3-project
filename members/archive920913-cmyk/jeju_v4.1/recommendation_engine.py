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

import json
import random
import re
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
                    slots.append({
                        "slot":   slot,
                        "place":  place,
                        "reason": self._reason(place, slot, preferences),
                    })
            itinerary.append({"day": day, "slots": slots})

        if self.ai:
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

        for idx, item in enumerate(schedule):
            day = item["day"]
            cat = self._activity_to_cat(item["activity"])
            slot = {"key": f"manual_{day}_{idx}", "label": item["activity"],
                    "time": item["time_slot"], "cat": cat, "kw": []}
            place = self._pick(df, cat, [], ulat, ulng, used, preferences)
            if place:
                used.add(place["name"])
                days.setdefault(day, []).append({
                    "slot": slot, "place": place,
                    "reason": self._reason(place, slot, preferences),
                })

        itinerary = [{"day": d, "slots": s} for d, s in sorted(days.items())]
        if self.ai:
            itinerary = self._ai_enrich(itinerary, preferences)
        return itinerary

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
        pref_hits = self._matched_preferences(place, preferences)
        slot_hits = self._matched_slot_keywords(place, slot)
        label = self._plain_label(slot)

        if pref_hits:
            reason = f"{', '.join(pref_hits)} 취향이 반영돼 {label} 일정에 잘 어울리는 장소예요."
        elif slot_hits:
            reason = f"{', '.join(slot_hits)} 분위기를 기대할 수 있어 {label} 코스로 잘 맞아요."
        else:
            category = str(place.get("category") or slot.get("cat") or "기타")
            fallback_map = {
                "카페": f"쉬어가기 좋은 분위기라 {label} 일정에 편하게 들르기 좋습니다.",
                "맛집": f"동선 안에서 식사 만족도를 기대할 수 있어 {label} 코스로 잘 맞습니다.",
                "자연": f"풍경과 산책을 즐기기 좋아 {label} 일정에 자연스럽게 어울립니다.",
                "문화": f"볼거리와 체험 요소가 있어 {label} 일정에 넣기 좋습니다.",
                "기타": f"이동 동선에 무리 없이 들르기 좋아 {label} 코스로 적합합니다.",
            }
            reason = fallback_map.get(category, f"{label} 일정 흐름에 잘 맞는 장소입니다.")

        return self._trim_reason(reason)

    @staticmethod
    def _trim_reason(reason: str, limit: int = 100) -> str:
        """추천 이유를 짧고 읽기 좋게 정리"""
        cleaned = " ".join(str(reason or "").split())
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[: limit - 3].rstrip(" ,.;") + "..."

    @staticmethod
    def _plain_label(slot: Dict) -> str:
        """이유 문장에 쓰기 좋게 슬롯 라벨을 정리"""
        label = str(slot.get("label", "이 일정"))
        cleaned = re.sub(r"[^0-9A-Za-z가-힣\s]", " ", label)
        return " ".join(cleaned.split()) or "이 일정"

    @staticmethod
    def _extract_terms(text: str) -> List[str]:
        """선호 키워드/CSV 키워드에서 비교 가능한 단어 추출"""
        seen = []
        for term in re.findall(r"[0-9A-Za-z가-힣]{2,}", str(text or "")):
            if term not in seen:
                seen.append(term)
        return seen

    def _matched_preferences(self, place: Dict, preferences: str) -> List[str]:
        """사용자 선호가 CSV 키워드/리뷰에 반영되는지 확인"""
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

    def _matched_slot_keywords(self, place: Dict, slot: Dict) -> List[str]:
        """시간대 슬롯 의도와 맞는 키워드 추출"""
        source = f"{place.get('keywords', '')} {place.get('reviews_text', '')}".lower()
        hits = []
        for keyword in slot.get("kw", []):
            normalized = str(keyword).strip()
            if normalized and normalized.lower() in source and normalized not in hits:
                hits.append(normalized)
            if len(hits) == 2:
                break
        return hits

    def _keyword_context(self, place: Dict, slot: Dict) -> List[str]:
        """AI 프롬프트용 핵심 키워드 요약"""
        slot_hits = self._matched_slot_keywords(place, slot)
        if slot_hits:
            return slot_hits

        keywords = []
        for term in self._extract_terms(place.get("keywords", "")):
            keywords.append(term)
            if len(keywords) == 4:
                break
        return keywords

    # ── 내부: 활동 → 카테고리 변환 ─────────────────────────
    @staticmethod
    def _activity_to_cat(activity: str) -> str:
        m = {"카페/디저트": "카페", "산책/자연": "자연",
             "관광/문화": "문화", "맛집": "맛집", "쇼핑/시장": "기타"}
        return m.get(activity, "기타")

    # ── OpenAI 추천 사유 보강 (선택) ─────────────────────────
    def _ai_enrich(self, itinerary: list, preferences: str) -> list:
        """OpenAI로 추천 사유 문장을 자연스럽게 보강 (코스 자체는 변경 안 함)"""
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
                "규칙:\n"
                "1. 각 reason은 한국어 한 문장, 100자 이내\n"
                "2. 평점, 별점, 리뷰 수, 데이터 개수는 언급하지 말 것\n"
                "3. slot_label과 category, keyword_hints, preference_hints를 바탕으로 왜 잘 맞는지 설명할 것\n"
                "4. 과장된 광고 문구, 이모지, 따옴표는 쓰지 말 것\n"
                "5. JSON 배열만 반환할 것\n"
                "형식 예시: [{\"day\":1,\"slot_key\":\"morning_cafe\",\"reason\":\"...\"}]\n"
                f"항목: {json.dumps(slots, ensure_ascii=False)}"
            )

            res = self.ai.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "너는 제주 여행 추천 이유를 짧고 자연스럽게 쓰는 편집자다."},
                    {"role": "user", "content": prompt},
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
            pass   # AI 실패해도 기본 reason 유지
        return itinerary

    def _parse_ai_reasons(self, content: str) -> Dict[tuple, str]:
        """OpenAI 응답 JSON 파싱"""
        cleaned = str(content or "").strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.DOTALL).strip()

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
