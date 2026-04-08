# 🚀 Team Project Template

AI Agent(Copilot 등)를 활용한 팀 프로젝트를 위한 템플릿입니다.
**개인 디렉토리 격리** 방식으로 Git 충돌을 원천 차단하고, Agent가 타인의 코드를 수정하지 못하도록 설계되었습니다.

---

## 📁 프로젝트 구조

```
ProjectTemplate/
├── README.md                     ← 이 파일
├── .gitignore
├── .github/
│   ├── copilot-instructions.md   ← Agent 전역 규칙
│   └── workflows/
│       └── path-check.yml        ← 경로 제한 자동 검사
├── members/
│   ├── _template/                ← 복사용 템플릿 (수정 금지)
│   │   ├── .copilot-instructions.md
│   │   ├── DEVLOG.md
│   │   ├── environment.yml
│   │   ├── README.md
│   │   └── src/
│   │       └── main.py
│   ├── alice/                    ← 멤버별 작업 공간 (예시)
│   └── bob/
├── integrated/                   ← 최종 통합 결과물 (팀장 관리)
│   ├── README.md
│   └── src/
├── docs/
│   └── SETUP.md                  ← 환경설정 가이드
└── scripts/
    └── add-member.sh             ← 멤버 등록 자동화 스크립트
```

---

## 🏁 시작 방법

### 1. 팀장: 레포지토리 생성

```bash
# 이 템플릿을 Fork 또는 Clone
git clone <이 레포지토리 URL>
cd ProjectTemplate

# 팀 이름에 맞게 레포 이름/설정 변경 후 본인 GitHub에 push
```

### 2. 팀원: 멤버 등록

```bash
# 팀장의 레포지토리를 Clone
git clone <팀 레포지토리 URL>
cd ProjectTemplate

# 자동 스크립트로 본인 디렉토리 생성
bash scripts/add-member.sh <본인-github-아이디>

# 변경사항 push
git add .
git commit -m "chore: <본인-아이디> 멤버 등록"
git push origin main
```

### 3. 작업 시작

```bash
# 본인 디렉토리로 이동
cd members/<본인-아이디>

# conda 환경 생성 및 활성화
conda env create -f environment.yml
conda activate <본인-아이디>-env

# 코딩 시작!
```

---

## 📜 규칙

### ⚠️ 절대 규칙

| 규칙 | 설명 |
|------|------|
| **자기 디렉토리만 수정** | `members/<본인-아이디>/` 내부만 수정 가능 |
| **타인 디렉토리 수정 금지** | 다른 멤버의 파일을 절대 수정하지 마세요 |
| **루트 파일 수정 금지** | `.gitignore`, `README.md` 등 루트 파일 수정 금지 |
| **_template 수정 금지** | `members/_template/`은 원본 보존용입니다 |

### 🤖 Agent 사용 규칙

- Agent(Copilot, Claude 등)는 **자동으로 본인 디렉토리만 수정**하도록 설정되어 있습니다
- 작업할 때마다 **DEVLOG.md**에 변경사항을 기록해주세요 (Agent가 자동으로 합니다)
- 다른 멤버의 코드를 참고만 하고, 수정은 하지 마세요

### 🔒 자동 보호

- **GitHub Actions**가 push 시 자동으로 경로를 검사합니다
- 본인 디렉토리 외부를 수정한 push는 **CI 실패** 처리됩니다

---

## 📝 DEVLOG (변경사항 기록)

각 멤버의 `DEVLOG.md`는 Agent가 코딩할 때 자동으로 업데이트합니다.

```markdown
## [2026-03-23]
### 작업자
- 🤖 Agent

### 변경 요약
- 로그인 기능 구현

### 수정된 파일
- `src/auth.py` — 로그인 함수 추가
- `src/main.py` — 라우터 연결

### 상태: ✅ 완료
```

이 기록은 **누가 무엇을 했는지** 추적하는 데 활용됩니다.
다른 팀원이 도와준 경우에는 `👥 팀원(@아이디) 도움`으로 표기하고, `도움받은 내용` 섹션에 구체적으로 기록합니다.

---

## 🔗 통합 프로젝트 (`integrated/`)

- 각 멤버가 완성한 코드를 **팀장이 통합**하는 디렉토리입니다
- 일반 멤버는 `integrated/` 디렉토리를 수정하지 마세요
- 통합 방법은 팀 내에서 논의하세요

---

## 📚 참고 문서

- [환경설정 가이드](docs/SETUP.md) — conda 설치, git 기초, 초기 설정 스텝바이스텝
- [멤버 템플릿 설명](members/_template/README.md) — 개인 디렉토리 구조 설명

---

## 🧑‍🤝‍🧑 팀원 목록

| 이름 | GitHub ID | 역할 | 디렉토리 |
|------|-----------|------|----------|
| (팀장 이름) | @github-id | 팀장 | `members/github-id/` |
| 피수민 | @PSM-0403 | 팀장 | members/PSM-0403 |
| 오경석 | @kyoungseok-Oh | 팀원 | members/kyoungseok-Oh |
| 김구 | @archive920913-cmyk | 팀원 | members/archive920913-cmyk |
| 안성민 | @CECode | 팀원 | members/CECode |

> 멤버 등록 시 위 표에 본인 정보를 추가해주세요.
