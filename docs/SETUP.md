# 🛠️ 환경설정 가이드

Git과 conda가 처음인 분들을 위한 스텝바이스텝 가이드입니다.

---

## 1. 사전 준비

### Git 설치

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install git -y

# macOS (Homebrew)
brew install git

# Windows → https://git-scm.com/download/win 에서 설치
```

### Git 기본 설정

```bash
# 본인 정보 등록 (최초 1회)
git config --global user.name "본인 이름"
git config --global user.email "본인@이메일.com"
```

### Conda 설치

[Miniconda 설치 페이지](https://docs.conda.io/en/latest/miniconda.html)에서 본인 OS에 맞는 버전을 설치하세요.

```bash
# 설치 확인
conda --version
```

---

## 2. 레포지토리 가져오기

```bash
# 팀 레포지토리를 Clone
git clone <팀 레포지토리 URL>
cd ProjectTemplate
```

---

## 3. 멤버 등록 (최초 1회)

```bash
# 자동 스크립트 실행 (GitHub 아이디 입력)
bash scripts/add-member.sh <본인-github-아이디>
```

이 스크립트가 하는 일:
- `members/_template/`을 `members/<본인-아이디>/`로 복사
- `.copilot-instructions.md`에 본인 아이디 자동 설정
- `environment.yml`의 환경 이름을 본인 아이디로 변경

### 수동으로 하고 싶다면:

```bash
# 1. 템플릿 복사
cp -r members/_template members/<본인-github-아이디>

# 2. environment.yml에서 환경 이름 변경
# name: member-env  →  name: <본인-아이디>-env
```

---

## 4. Conda 환경 생성

```bash
cd members/<본인-아이디>

# 환경 생성
conda env create -f environment.yml

# 환경 활성화
conda activate <본인-아이디>-env

# 패키지 추가 시
conda install <패키지명>

# environment.yml 업데이트 (패키지 추가 후 꼭 해주세요!)
conda env export --no-builds > environment.yml
```

---

## 5. 일상적인 작업 흐름

### 작업 시작 전

```bash
# 1. 최신 코드 가져오기
git pull origin main

# 2. 본인 디렉토리로 이동
cd members/<본인-아이디>

# 3. conda 환경 활성화
conda activate <본인-아이디>-env
```

### 작업 완료 후

```bash
# 1. 변경사항 확인
git status

# 2. 본인 디렉토리만 add (중요!)
git add members/<본인-아이디>/

# 3. 커밋
git commit -m "feat: 기능 설명"

# 4. push
git push origin main
```

### ⚠️ push 실패 시

```bash
# 다른 사람이 먼저 push한 경우
git pull --rebase origin main

# 충돌이 없다면 자동 해결됨 → 다시 push
git push origin main
```

---

## 6. 커밋 메시지 규칙 (권장)

```
feat: 새 기능 추가
fix: 버그 수정
docs: 문서 수정
chore: 설정/환경 변경
refactor: 코드 리팩토링
test: 테스트 코드
```

예시:
```
feat: 로그인 API 구현
fix: 데이터 파싱 오류 수정
docs: DEVLOG 업데이트
chore: numpy 패키지 추가
```

---

## 7. 자주 하는 실수 & 해결법

### ❌ 다른 사람 디렉토리를 실수로 수정했을 때

```bash
# 수정 전 상태로 되돌리기
git checkout -- members/<다른사람>/

# 또는 본인 디렉토리만 선택적으로 add
git add members/<본인-아이디>/
git commit -m "feat: 내 작업만 커밋"
```

### ❌ git push가 rejected 될 때

```bash
git pull --rebase origin main
git push origin main
```

### ❌ conda 환경이 꼬였을 때

```bash
conda deactivate
conda env remove -n <본인-아이디>-env
conda env create -f members/<본인-아이디>/environment.yml
conda activate <본인-아이디>-env
```

---

## 8. VS Code + Copilot 설정

1. VS Code에서 프로젝트 폴더를 엽니다
2. Copilot 확장이 설치되어 있으면 자동으로 `.copilot-instructions.md`를 인식합니다
3. Agent가 본인 디렉토리만 수정하도록 자동 제한됩니다
4. 작업하면 `DEVLOG.md`가 자동 업데이트됩니다

---

## 도움이 필요하면?

- 팀장에게 먼저 물어보세요

---

## 9. 팀원 협업 가이드

다른 팀원이 내 코드를 도와주는 상황은 자주 나타납니다.

### 원칙

> **내 디렉토리는 내가 commit & push** — 도와주는 사람이 직접 push하면 CI가 차단합니다.

### 시나리오별 방법

#### 함께 화면 보면서 도움받기 (가장 간단)

1. 팀원 B가 내(A) 디렉토리에서 **함께 코드 수정** (화면 공유 / VS Code Live Share 등)
2. **내가(A) 직접** commit & push
3. DEVLOG에 기록:
   ```markdown
   ### 작업자
   - 👥 팀원(@bob) 도움

   ### 도움받은 내용
   - @bob 이 데이터 파싱 로직 버그 원인 분석 및 수정 도움
   ```

#### 팀원이 코드를 작성해서 보내준 경우

1. 팀원 B가 코드 조각을 메신저/이메일/파일로 전달
2. **내가(A) 직접** 내 파일에 반영 후 commit & push
3. DEVLOG에 기록:
   ```markdown
   ### 작업자
   - 👥 팀원(@bob) 도움

   ### 도움받은 내용
   - @bob 이 정규표현식 유틸 함수 코드를 작성해서 전달해줌
   ```

#### Agent로 작업한 경우

- Agent가 자동으로 `🤖 Agent`로 기록
- 사용자가 나중에 직접 수정한 부분이 있으면 `👤 본인`으로 추가 기록

### ⚠️ 주의: 절대 하면 안 되는 것

- 팀원 B가 A의 디렉토리를 수정해서 **B의 계정으로 push** → CI 실패
- A의 파일을 B의 디렉토리로 복사해서 수정 → 통합 시 혼란

---

## 10. Windows (Git Bash) 사용자 주의사항

### Git Bash 설치 확인

Git for Windows 설치 시 Git Bash가 함께 설치됩니다.

### 줄바꿈(CRLF) 설정 (중요!)

Windows는 줄바꿈에 `\r\n`(CRLF)을 사용하는데, 이것이 쉘 스크립트나 코드에 문제를 일으킬 수 있습니다.

```bash
# 최초 1회 설정 — commit 시 LF, checkout 시 원본 유지
git config --global core.autocrlf input
```

### 스크립트 실행

```bash
# Git Bash 터미널에서 실행
bash scripts/add-member.sh <본인-아이디>
```

> 💡 VS Code 터미널에서도 쉘을 Git Bash로 변경하면 동일하게 사용 가능합니다.
> 터미널 우측 상단 `+` 옆 드롭다운 → `Git Bash` 선택

### conda 사용 시

Git Bash에서 conda가 인식되지 않으면:

```bash
# conda init을 한 번 실행
conda init bash
# 터미널 재시작 후 사용
```

또는 **Anaconda Prompt** 에서 conda 명령을 실행하고, Git Bash에서는 git 명령만 사용하는 것도 방법입니다.
- Git 기초: [Git 간편안내서](https://rogerdudler.github.io/git-guide/index.ko.html)
- Conda 기초: [Conda Cheat Sheet](https://docs.conda.io/projects/conda/en/latest/user-guide/cheatsheet.html)
