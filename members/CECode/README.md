
# 🏝️ 제주 여행 맞춤 추천 시스템 v3.2
```(현재 이 경로의 파일들은 전부 AI가 작성한 코드들입니다.)```

**AI가 추천하는 자연스러운 여행 일정!** 🤖
## 🆕 v3.2 주요 개선사항

### 1. 🔒 보안 강화
- ✅ API 키를 `.env` 파일로 관리 (Git에 노출되지 않음)
- ✅ UI에서 API 키 입력 기능 제거
- ✅ `python-dotenv`로 환경변수 자동 로드

### 2. 🎯 정확한 경로 계산
- ✅ **카카오 네비게이션 API 통합** (실제 도로 거리/시간)
- ✅ API 할당량 초과 시 자동으로 추정치 사용
- ✅ 정확도 표시: "🎯 실제 경로" vs "📏 예상치"

### 3. 📝 코드 가독성 개선
- ✅ 모든 함수에 상세한 주석 추가
- ✅ 기능별로 명확하게 구분된 섹션
- ✅ 타입 힌트 및 설명 포함

### 4. 🎨 UI 개선
- ✅ 동선 표시 제거 (단순화)
- ✅ 이동 정보를 더 명확하게 표시
- ✅ 경로 구간별 상세 정보 제공

---

## 📌 핵심 특징

### ✨ 완전히 새로운 AI 추천!

1. **🤖 ChatGPT 기반 추천**
   - GPT-4o-mini 모델 사용
   - 동선, 시간대, 카테고리 종합 분석
   - 사용자 취향 100% 반영
   - 비용: 한 번에 10~40원 (저렴!)

2. **🚗 정확한 경로 계산**
   - 카카오 네비게이션 API 사용
   - 실제 도로 거리와 소요 시간
   - 통행료 및 예상 택시비 정보
   - API 사용 불가 시 자동으로 추정치 제공

3. **🏨 완벽한 숙소 검색**
   - 호텔명으로 검색: "제주 하얏트", "신라호텔"
   - 주소로 검색: "제주시 연동", "서귀포시 중문관광로 72번길 75"
   - 좌표로 검색: "33.4996, 126.5312"
   - 카카오 주소 검색 API 활용

4. **⏰ 자연스러운 시간대별 추천**
   ```
   08:00  ☕ 모닝 커피  → AI가 선택한 카페
   10:00  🌅 오전 관광  → 동선 고려 관광지
   12:00  🍽️ 점심 식사  → 선호도 반영 맛집
   14:00  🏖️ 오후 관광  → 연계성 있는 명소
   17:00  ☕ 카페 휴식  → 전망 좋은 카페
   18:30  🍖 저녁 식사  → AI 추천 맛집
   20:30  🍺 밤 한잔    → 분위기 좋은 술집
   ```

5. **📋 풍부한 상세 정보**
   - ⏰ 운영시간 (실시간 영업 상태)
   - ⭐ 평점 및 리뷰 수
   - 📷 대표 사진
   - 🚗 정확한 경로 정보 (거리, 시간)

---

## 🗂️ 파일 구조

```
jeju_travel_v3.2/
├── .env                         # API 키 설정 (비공개)
├── .env.example                 # API 키 템플릿
├── .gitignore                   # Git 제외 파일
├── app.py                       # 메인 앱
├── config.py                    # 설정 (dotenv 사용)
├── kakao_service.py             # 카카오 API (네비게이션 API 추가)
├── data_manager.py              # 데이터 관리
├── recommendation_engine.py     # AI 추천 엔진
├── ui_components.py             # UI 컴포넌트 (동선 제거)
├── festival_data.py             # 축제 데이터
├── requirements.txt             # 패키지 (python-dotenv 추가)
├── README.md                    # 이 파일
└── jeju_places_final_fixed.csv  # 장소 데이터 (1,269개)
```

---

## 🚀 빠른 시작

### 1. 패키지 설치

```bash
pip install -r requirements.txt
```

### 2. API 키 설정

`.env` 파일을 생성하고 API 키를 입력하세요:

```bash
# .env 파일 생성
cp .env.example .env

# 텍스트 에디터로 .env 파일 열기
nano .env  # 또는 vim, code 등
```

`.env` 파일 내용:

```env
# 카카오 REST API 키 (필수)
KAKAO_API_KEY=
# OpenAI API 키 (선택 - AI 추천용)
OPENAI_API_KEY
# OpenAI 모델 설정
OPENAI_MODEL=gpt-4o-mini
```

⚠️ **중요**: `.env` 파일은 절대 Git에 커밋하지 마세요!

### 3. 실행

```bash
streamlit run app.py
```

브라우저가 자동으로 열립니다! 🎉

---

## 📖 사용 방법

### Step 1: 숙소 검색

✅ **모든 형태로 검색 가능!**

- 호텔명: "제주 신라호텔", "하얏트 리젠시"
- 주소: "제주시 연동 312-1"
- 도로명: "서귀포시 중문관광로 72번길 75"
- 좌표: "33.4996, 126.5312"

### Step 2: 설정

- 여행 기간: 1~4일
- 검색 반경: 5~50km
- 카테고리: 맛집, 카페, 관광명소

### Step 3: AI 추천 설정 (선택)

**OpenAI API가 있으면:**
1. ✅ "AI 기반 최적화 사용" 체크
2. 선호 사항 입력:
   - "해산물 좋아함"
   - "자연 경관 중심"
   - "카페는 오션뷰 선호"

### Step 4: 추천 받기

"🎯 추천 코스 생성" 클릭!

**AI 사용 시:**
- 🤖 "AI가 최적의 여행 코스를 분석 중입니다..."
- 3~5초 후 AI 최적화 완료!
- 각 장소에 "AI 추천" 표시

---

## 💡 AI vs 기본 추천 비교

| 항목 | 기본 추천 | AI 추천 🤖 |
|------|----------|-----------|
| **추천 방식** | 거리순 | ChatGPT 분석 |
| **동선 최적화** | ★★☆☆☆ | ★★★★★ |
| **선호도 반영** | ❌ | ✅ |
| **시간대 고려** | 기본 | 고급 |
| **비용** | 무료 | ~40원/회 |
| **속도** | <1초 | 3~5초 |
| **경로 정확도** | 추정치 | 카카오 네비 API |

---

## 🎨 v3.2 개선 포인트

| 항목 | v3.1 | v3.2 | 개선 |
|------|------|------|------|
| API 키 관리 | UI 입력 | .env 파일 | ✅ 보안 강화 |
| 경로 계산 | 추정치 | 카카오 네비 API | ✅ 정확도 향상 |
| 코드 주석 | 기본 | 상세 | ✅ 가독성 개선 |
| 동선 표시 | 있음 | 제거 | ✅ UI 단순화 |

---

## 🔍 주요 코드 하이라이트

### 1. 카카오 네비게이션 API 사용

```python
def get_navigation_route(
    self,
    origin_lat: float,
    origin_lng: float,
    destination_lat: float,
    destination_lng: float
) -> Optional[Dict]:
    """
    카카오 네비게이션 API로 정확한 경로 정보를 가져옵니다
    
    ⭐ 이 함수가 실제 카카오맵 네비게이션에서 사용하는 거리/시간을 반환합니다!
    """
    url = f'{self.navi_url}/v1/directions'
    params = {
        'origin': f'{origin_lng},{origin_lat}',
        'destination': f'{destination_lng},{destination_lat}',
        'priority': 'RECOMMEND',
    }
    
    response = requests.get(url, headers=self.headers, params=params, timeout=10)
    data = response.json()
    
    # 정확한 거리/시간 추출
    summary = data['routes'][0]['summary']
    return {
        'distance_km': summary['distance'] / 1000,
        'duration_minutes': summary['duration'] / 60,
        'is_accurate': True
    }
```

### 2. 환경변수 로드 (python-dotenv)

```python
from dotenv import load_dotenv
import os

# .env 파일에서 환경변수 로드
load_dotenv()

# API 키 가져오기
KAKAO_API_KEY = os.getenv("KAKAO_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
```

### 3. 정확도 표시

```python
if route_from_previous:
    is_accurate = route_from_previous.get('is_accurate', False)
    accuracy_label = "🎯 실제 경로" if is_accurate else "📏 예상치"
    
    route_text = (
        f"🚗 {origin} → {name} · "
        f"{accuracy_label} · "
        f"{format_duration(duration_min)} · "
        f"{distance_km:.1f}km"
    )
    st.caption(route_text)
```

---

## ❓ 자주 묻는 질문

### Q1. .env 파일은 어디에 두나요?
A. 프로젝트 루트 디렉토리에 두세요 (app.py와 같은 폴더).

### Q2. API 키가 노출될까 걱정됩니다.
A. `.gitignore`에 `.env`가 포함되어 있어 Git에 커밋되지 않습니다.

### Q3. 카카오 네비게이션 API는 무료인가요?
A. 카카오 모빌리티 API는 유료입니다. 무료 할당량 초과 시 자동으로 추정치를 사용합니다.

### Q4. OpenAI API 비용이 얼마나 들나요?
A. 한 번 추천에 약 10~40원 정도입니다. 월 $5 무료 크레딧으로 125~500회 사용 가능합니다.

### Q5. AI 추천이 필수인가요?
A. 아니요. OpenAI API 키가 없어도 기본 추천 기능을 사용할 수 있습니다.

---

## 🔜 향후 계획

- [x] AI 기반 추천 완성
- [x] 주소 검색 최적화
- [x] OpenAI API 통합
- [x] 카카오 네비게이션 API 통합
- [x] 코드 주석 및 가독성 개선
- [ ] 개별 리프레시 완성
- [ ] 리뷰 더 많이 수집
- [ ] 경로 최적화 고도화

---

## 📄 라이선스

MIT License - 자유롭게 사용하세요!

---

## 🙏 감사합니다!

**AI가 추천하는 완벽한 제주 여행을 즐기세요!** 🏝️✨

Made with ❤️ + 🤖 ChatGPT + 🚗 Kakao Navi API
