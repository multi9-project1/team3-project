#!/bin/bash
# =============================================================================
# 멤버 등록 스크립트
# 사용법: bash scripts/add-member.sh <github-아이디>
# =============================================================================

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 프로젝트 루트로 이동
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# 인자 확인
if [ -z "$1" ]; then
    echo -e "${RED}❌ 사용법: bash scripts/add-member.sh <github-아이디>${NC}"
    echo ""
    echo "예시:"
    echo "  bash scripts/add-member.sh alice"
    echo "  bash scripts/add-member.sh bob"
    exit 1
fi

MEMBER_NAME="$1"
MEMBER_DIR="members/${MEMBER_NAME}"
TEMPLATE_DIR="members/_template"

# 템플릿 존재 확인
if [ ! -d "$TEMPLATE_DIR" ]; then
    echo -e "${RED}❌ 템플릿 디렉토리를 찾을 수 없습니다: ${TEMPLATE_DIR}${NC}"
    exit 1
fi

# 이미 존재하는지 확인
if [ -d "$MEMBER_DIR" ]; then
    echo -e "${YELLOW}⚠️  이미 존재하는 멤버 디렉토리입니다: ${MEMBER_DIR}${NC}"
    echo "다시 생성하려면 먼저 삭제하세요: rm -rf ${MEMBER_DIR}"
    exit 1
fi

echo -e "${GREEN}🚀 멤버 등록을 시작합니다: ${MEMBER_NAME}${NC}"
echo ""

# 1. 템플릿 복사
echo "📁 템플릿 복사 중..."
cp -r "$TEMPLATE_DIR" "$MEMBER_DIR"

# 2. 플레이스홀더 치환
echo "✏️  설정 파일 업데이트 중..."

# sed -i 대신 임시파일 패턴 사용 (Git Bash/Windows 호환)
safe_sed() {
    local pattern="$1"
    local file="$2"
    local tmp="${file}.tmp"
    sed "$pattern" "$file" > "$tmp" && mv "$tmp" "$file"
}

# .copilot-instructions.md 내 {MEMBER_NAME} 치환
if [ -f "${MEMBER_DIR}/.copilot-instructions.md" ]; then
    safe_sed "s/{MEMBER_NAME}/${MEMBER_NAME}/g" "${MEMBER_DIR}/.copilot-instructions.md"
fi

# README.md 내 {MEMBER_NAME} 치환
if [ -f "${MEMBER_DIR}/README.md" ]; then
    safe_sed "s/{MEMBER_NAME}/${MEMBER_NAME}/g" "${MEMBER_DIR}/README.md"
fi

# src/main.py 내 {MEMBER_NAME} 치환
if [ -f "${MEMBER_DIR}/src/main.py" ]; then
    safe_sed "s/{MEMBER_NAME}/${MEMBER_NAME}/g" "${MEMBER_DIR}/src/main.py"
fi

# environment.yml 의 환경 이름 변경
if [ -f "${MEMBER_DIR}/environment.yml" ]; then
    safe_sed "s/name: member-env/name: ${MEMBER_NAME}-env/g" "${MEMBER_DIR}/environment.yml"
fi

echo ""
echo -e "${GREEN}✅ 멤버 등록 완료!${NC}"
echo ""
echo "📂 생성된 디렉토리: ${MEMBER_DIR}/"
echo ""
echo "다음 단계:"
echo "  1. conda 환경 생성:"
echo "     cd ${MEMBER_DIR}"
echo "     conda env create -f environment.yml"
echo "     conda activate ${MEMBER_NAME}-env"
echo ""
echo "  2. 변경사항 commit & push:"
echo "     git add members/${MEMBER_NAME}/"
echo "     git commit -m \"chore: ${MEMBER_NAME} 멤버 등록\""
echo "     git push origin main"
echo ""
echo "  3. 코딩 시작! 🎉"
echo "     src/main.py 파일부터 시작하세요"
