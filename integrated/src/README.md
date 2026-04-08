# 🍊 제주 여행 맞춤 추천 시스템 v4.0

팀이 직접 수집한 CSV 데이터와 카카오 API, OpenAI를 결합하여 제주 여행 일정을 자동으로 추천해주는 Streamlit 웹 앱입니다.

---

## 주요 기능

- **숙소 검색**: 카카오 API로 숙소명·브랜드명·주소를 실시간 검색하여 출발지 설정
- **여행 기간 설정**: 최대 7일 일정, 날짜 범위 선택
- **카테고리 필터**: 원하는 장소 카테고리만 선택해 추천 범위 설정
- **AI 맞춤 조건**: 일차별 슬롯(아침 카페, 오전 관광, 점심, 오후 관광, 오후 카페, 저녁)에 취향 키워드 입력
- **추천 반경 설정**: 숙소 기준 5~60km 반경 내 장소 필터링
- **자동 코스 생성**: 조건에 맞는 여행 코스를 일차별로 자동 생성
- **결과 시각화**:
  - 일차별 탭: 장소 상세 정보 및 카카오 지도 경로 연동
  - 전체 지도 탭: Folium 지도에 일차별 색상 구분 마커 표시
  - 코스 분석 탭: 추천 결과 통계 및 분석
- **AI 챗봇**: OpenAI 기반 챗봇으로 추천 코스 관련 질문 가능
- **Chroma 벡터 DB**: 리뷰 유사도 분석으로 취향 키워드 반영 정확도 향상

---

## 설치 및 실행

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. API 키 설정

`.env.example`을 복사해 `.env`로 이름을 바꾸고 API 키를 입력합니다.

```bash
cp .env.example .env
```

```env
KAKAO_API_KEY=여기에_카카오_REST_API_키_입력
OPENAI_API_KEY=여기에_OpenAI_API_키_입력   # 선택사항
OPENAI_MODEL=gpt-4o-mini
```

- 카카오 REST API 키: [https://developers.kakao.com](https://developers.kakao.com)
- OpenAI API 키: [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys) (없으면 기본 추천만 동작)

### 3. (선택) Chroma 벡터 DB 빌드

취향 키워드 유사도 검색 기능을 사용하려면 먼저 실행합니다.

```bash
python build_chroma.py
```

### 4. 앱 실행

```bash
streamlit run app.py
```

---

## 프로젝트 구조

```
project/
├── app.py                  # 메인 앱 (Streamlit UI)
├── config.py               # 페이지 설정, 카테고리, API 키 로드
├── data_manager.py         # CSV 데이터 로딩 및 관리
├── kakao_service.py        # 카카오 API 연동 (숙소 검색, 지도)
├── recommendation_engine.py# 여행 코스 자동 추천 엔진
├── ui_components.py        # 일차별 코스, 지도, 분석 UI 컴포넌트
├── chatbot.py              # OpenAI 기반 AI 챗봇
├── chroma_retriever.py     # Chroma 벡터 DB 검색
├── build_chroma.py         # Chroma DB 빌드 스크립트
├── jeju_crawling_100.csv   # 팀 직접 수집 제주 장소 데이터
├── chroma_jeju_reviews/    # Chroma 벡터 DB 파일
├── .env.example            # 환경변수 예시 파일
└── requirements.txt        # 의존성 목록
```

---

## 사용 기술

| 구분 | 기술 |
|------|------|
| UI 프레임워크 | Streamlit |
| 지도 시각화 | Folium, streamlit-folium |
| 장소 검색 | 카카오 REST API |
| AI 추천 / 챗봇 | OpenAI API (gpt-4o-mini) |
| 리뷰 유사도 검색 | ChromaDB, LangChain |
| 데이터 처리 | Pandas |

---

## 데이터 출처

- **CSV 데이터** (`jeju_crawling_100.csv`): 팀이 직접 수집한 제주 장소 정보 (장소명, 주소, 평점, 리뷰, 키워드)
- **카카오 API**: 숙소 검색, 네비 경로, 지도 링크 (실시간)
