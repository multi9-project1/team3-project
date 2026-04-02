# 🚀 3분 빠른 시작 가이드

제주 여행 추천 시스템을 3분 안에 실행하는 방법!

---

## ⚡ Step 1: 파일 확인 (10초)

다음 파일들이 같은 폴더에 있는지 확인하세요:

```
📁 jeju_travel_v3.2/
  ├── .env                        ✅ API 키 설정 (비공개)
  ├── .env.example                ✅ API 키 템플릿
  ├── .gitignore                  ✅ Git 제외 파일
  ├── app.py                      ✅ 메인 앱 (AI 통합)
  ├── config.py                   ✅ 설정 (dotenv 사용)
  ├── kakao_service.py            ✅ 카카오 API (네비게이션 API 추가)
  ├── data_manager.py             ✅ 데이터 관리
  ├── recommendation_engine.py    ✅ 추천 엔진 (AI 기반)
  ├── ui_components.py            ✅ UI (동선 제거)
  ├── festival_data.py            ✅ 축제 데이터
  ├── requirements.txt            ✅ 패키지 목록
  ├── jeju_places_final_fixed.csv ✅ 장소 데이터
  ├── README.md                   ✅ 설명서
  └── QUICKSTART.md               ✅ 이 파일
```

---

## ⚡ Step 2: 패키지 설치 (1분)

터미널에서:

```bash
pip install -r requirements.txt
```

**설치되는 패키지들**:
- streamlit (웹 UI)
- pandas (데이터 처리)
- folium (지도)
- requests (API 통신)
- beautifulsoup4 (크롤링)
- openai (AI 추천) ⭐
- **python-dotenv (환경변수 관리)** ⭐ 신규!

---

## ⚡ Step 3: API 키 설정 (1분)

### 방법 1: .env 파일 생성 (추천) ⭐

```bash
# .env.example을 복사하여 .env 파일 생성
cp .env.example .env

# 텍스트 에디터로 .env 파일 열기
nano .env  # 또는 vim, code 등
```

`.env` 파일에 API 키 입력:

```env
# 카카오 REST API 키 (필수)
KAKAO_API_KEY=2d324ca2e1934cfeb7a09694886cf3f7

# OpenAI API 키 (선택 - AI 추천용)
OPENAI_API_KEY=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

# OpenAI 모델 설정
OPENAI_MODEL=gpt-4o-mini
```

⚠️ **중요**: `.env` 파일은 절대 Git에 커밋하지 마세요!

### API 키 발급 방법

**1) 카카오 API** (필수 - 5분)
1. https://developers.kakao.com 접속
2. 로그인 → "내 애플리케이션" → "애플리케이션 추가하기"
3. 앱 이름: "제주여행"
4. **REST API 키** 복사

**2) OpenAI API** (선택 - AI 추천용 - 5분)
1. https://platform.openai.com/api-keys 접속
2. 로그인 → "Create new secret key"
3. 이름: "jeju-travel"
4. **API 키** 복사 (sk-로 시작)

💡 **비용**: 한 번 추천에 약 $0.01~0.03 (약 10~40원)

---

## ⚡ Step 4: 실행! (10초)

```bash
streamlit run app.py
```

브라우저가 자동으로 열립니다! 🎉

---

## 📝 첫 추천 받기

### 🔥 v3.2 새로운 기능!

**1. 자동 API 키 로드**
- UI에서 API 키를 입력할 필요 없음!
- .env 파일에서 자동으로 로드됨

**2. 정확한 경로 계산**
- 카카오 네비게이션 API 사용
- 실제 도로 거리와 소요 시간
- "🎯 실제 경로" vs "📏 예상치" 표시

**3. 단순화된 UI**
- 동선 표시 제거
- 이동 정보를 더 명확하게 표시

---

### 방법 1: 기본 추천 (OpenAI API 키 없이)

1. **사이드바**에서 "🏨 숙소 기준 위치" 찾기
2. 검색창에 아무거나 입력 (예: "제주시")
3. **카테고리 선택** (맛집, 카페, 관광명소)
4. **"🎯 추천 코스 생성"** 클릭

✅ CSV 데이터만으로 기본 추천!

---

### 방법 2: AI 추천 (추천!) 🤖

#### A. 기준 위치 검색

**사이드바**에서 "📍 기준 위치" 입력:
- 호텔명: "제주 신라호텔", "하얏트 리젠시"
- 주소: "제주시 연동 312-1", "서귀포시 중문관광로 72번길"
- 좌표: "33.4996, 126.5312"

**"🔍 기준 위치 설정"** 클릭 → ✅ 검색 성공!

#### B. 설정

1. 여행 일정, 반경, 카테고리 선택
2. **🤖 AI 맞춤 추천** 섹션에서:
   - ✅ "AI 기반 최적화 사용" 체크
   - 선호 사항 입력 (예: "해산물 좋아함, 자연 경관 중심")

#### C. 추천 받기!

**"🎯 추천 코스 생성"** 클릭!

1. 🤖 "AI가 최적의 여행 코스를 분석 중입니다..." 표시
2. ✅ AI가 추천한 최적 코스 확인!
3. 🎯 정확한 경로 정보 표시 (카카오 네비 API)

---

## ✨ v3.2 vs v3.1 비교

| 특징 | v3.1 | v3.2 🆕 |
|------|------|---------|
| API 키 관리 | UI 입력 | .env 자동 로드 |
| 경로 계산 | 추정치 | 카카오 네비 API |
| 코드 주석 | 기본 | 상세 |
| 동선 표시 | 있음 | 제거 (단순화) |
| 보안 | 중간 | 강화 |

---

## ❓ 문제 해결

### "No module named 'dotenv'" 에러

```bash
pip install python-dotenv
```

### "No module named 'openai'" 에러

```bash
pip install openai
```

### AI 추천이 안 돼요

→ OpenAI API 키를 `.env` 파일에 입력했나요?
→ "AI 기반 최적화 사용" 체크했나요?

### 주소 검색이 안 돼요

✅ **v3.2에서 완벽하게 작동합니다!**

- 도로명 주소: "제주시 중앙로 123"
- 지번 주소: "제주시 연동 312-1"
- 호텔명: "제주 신라호텔"
- 좌표: "33.4996, 126.5312"

모두 검색 가능!

### 경로 정보가 "📏 예상치"로 표시돼요

→ 카카오 네비게이션 API 할당량이 초과되었습니다.
→ 추정치도 충분히 정확하니 안심하세요!

### OpenAI API 비용이 걱정돼요

- 한 번 추천: 약 10~40원
- 월 $5 크레딧 제공
- 약 125~500회 무료 사용 가능!

---

## 💡 팁

1. **첫 실행**: .env 파일만 제대로 설정하면 OK!
2. **AI 추천**: OpenAI API 추가하면 훨씬 좋아짐!
3. **선호도 입력**: 구체적일수록 AI가 더 잘 추천
4. **속도**: AI 추천은 3~5초 소요
5. **보안**: .env 파일은 Git에 커밋하지 마세요!

---

## 🎓 다음 단계

1. **기본 추천 테스트** → 작동 확인
2. **AI 추천 비교** → 차이 경험
3. **경로 정확도** → 카카오 네비 API vs 추정치
4. **코드 수정** → 자신만의 기능 추가

---

## 🚀 준비 완료!

이제 AI가 추천하는 완벽한 제주 여행을 계획해보세요! 🏝️

**Happy Traveling! ✈️**
