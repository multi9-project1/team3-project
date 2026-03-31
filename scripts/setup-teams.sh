#!/bin/bash
# =============================================================================
# 팀별 레포지토리 자동 세팅 스크립트 (강사용)
# 사용법: bash scripts/setup-teams.sh <organization> <팀수>
# 예시:   bash scripts/setup-teams.sh multi9-project1 3
#
# 사전 조건:
#   1. GitHub Organization이 이미 생성되어 있어야 합니다
#   2. GitHub CLI(gh)가 설치 및 인증되어 있어야 합니다
#      - 설치: https://cli.github.com/
#      - 인증: gh auth login
# =============================================================================

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# 프로젝트 루트로 이동
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# ─── 인자 확인 ───
if [ -z "$1" ] || [ -z "$2" ]; then
    echo -e "${RED}❌ 사용법: bash scripts/setup-teams.sh <organization> <팀수>${NC}"
    echo ""
    echo "예시:"
    echo "  bash scripts/setup-teams.sh multi9-project1 3"
    echo ""
    echo "사전 조건:"
    echo "  1. GitHub Organization이 이미 생성되어 있어야 합니다"
    echo "  2. gh (GitHub CLI) 설치 및 인증: gh auth login"
    exit 1
fi

ORG_NAME="$1"
TEAM_COUNT="$2"

# 숫자 검증
if ! [[ "$TEAM_COUNT" =~ ^[0-9]+$ ]] || [ "$TEAM_COUNT" -lt 1 ]; then
    echo -e "${RED}❌ 팀 수는 1 이상의 숫자여야 합니다${NC}"
    exit 1
fi

# ─── gh CLI 확인 ───
if ! command -v gh &> /dev/null; then
    echo -e "${RED}❌ GitHub CLI(gh)가 설치되어 있지 않습니다${NC}"
    echo ""
    echo "설치 방법:"
    echo "  Windows: winget install GitHub.cli"
    echo "  macOS:   brew install gh"
    echo "  Linux:   https://github.com/cli/cli/blob/trunk/docs/install_linux.md"
    echo ""
    echo "설치 후 인증:"
    echo "  gh auth login"
    exit 1
fi

# gh 인증 확인
if ! gh auth status &> /dev/null 2>&1; then
    echo -e "${RED}❌ GitHub CLI 인증이 필요합니다${NC}"
    echo "  gh auth login 을 먼저 실행하세요"
    exit 1
fi

echo -e "${CYAN}══════════════════════════════════════════${NC}"
echo -e "${CYAN}  팀 레포지토리 자동 세팅${NC}"
echo -e "${CYAN}  Organization: ${ORG_NAME}${NC}"
echo -e "${CYAN}  팀 수: ${TEAM_COUNT}${NC}"
echo -e "${CYAN}══════════════════════════════════════════${NC}"
echo ""

# ─── 임시 디렉토리 준비 ───
WORK_DIR=$(mktemp -d)
trap "rm -rf $WORK_DIR" EXIT

# 템플릿 파일 준비 (현재 프로젝트에서 복사)
echo -e "${GREEN}📦 템플릿 준비 중...${NC}"
TEMPLATE_DIR="$WORK_DIR/template"
mkdir -p "$TEMPLATE_DIR"

# .git 제외하고 프로젝트 파일 복사
rsync -a --exclude='.git' --exclude='scripts/setup-teams.sh' "$PROJECT_ROOT/" "$TEMPLATE_DIR/"

# ─── 팀별 레포 생성 ───
for i in $(seq 1 "$TEAM_COUNT"); do
    REPO_NAME="team${i}-project"
    FULL_REPO="${ORG_NAME}/${REPO_NAME}"

    echo ""
    echo -e "${YELLOW}────────────────────────────────────${NC}"
    echo -e "${GREEN}🚀 [${i}/${TEAM_COUNT}] ${FULL_REPO} 생성 중...${NC}"
    echo -e "${YELLOW}────────────────────────────────────${NC}"

    # 레포가 이미 존재하는지 확인
    if gh repo view "$FULL_REPO" &> /dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  이미 존재합니다: ${FULL_REPO} — 건너뜁니다${NC}"
        continue
    fi

    # 1. GitHub에 빈 레포 생성
    echo "  📁 레포지토리 생성..."
    gh repo create "$FULL_REPO" \
        --public \
        --description "Team ${i} Project — multi9-project1" \
        --clone=false

    # 2. 로컬에 복사 후 push
    REPO_DIR="$WORK_DIR/$REPO_NAME"
    cp -r "$TEMPLATE_DIR" "$REPO_DIR"

    cd "$REPO_DIR"

    # README.md 팀 이름 반영
    safe_sed() {
        local pattern="$1"
        local file="$2"
        local tmp="${file}.tmp"
        sed "$pattern" "$file" > "$tmp" && mv "$tmp" "$file"
    }

    safe_sed "s/Team Project Template/Team ${i} Project/g" "README.md"

    # git 초기화 및 push
    echo "  📤 코드 업로드..."
    git init -q
    git checkout -b main
    git add .
    git commit -q -m "chore: team${i} 프로젝트 초기 세팅"
    git remote add origin "https://github.com/${FULL_REPO}.git"
    git push -u origin main -q

    cd "$PROJECT_ROOT"

    echo -e "${GREEN}  ✅ ${FULL_REPO} 완료!${NC}"
    echo "     https://github.com/${FULL_REPO}"
done

echo ""
echo -e "${CYAN}══════════════════════════════════════════${NC}"
echo -e "${GREEN}🎉 모든 팀 레포지토리 생성 완료!${NC}"
echo -e "${CYAN}══════════════════════════════════════════${NC}"
echo ""
echo "📋 생성된 레포지토리:"
for i in $(seq 1 "$TEAM_COUNT"); do
    echo "  Team ${i}: https://github.com/${ORG_NAME}/team${i}-project"
done
echo ""
echo "다음 단계:"
echo "  1. 각 팀장에게 해당 레포 URL 전달"
echo "  2. 팀원들은 clone 후 bash scripts/add-member.sh <아이디> 실행"
echo "  3. 강사 모니터링: bash scripts/monitor-teams.sh ${ORG_NAME} ${TEAM_COUNT}"
