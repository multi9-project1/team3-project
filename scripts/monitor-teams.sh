#!/bin/bash
# =============================================================================
# 강사용 팀 모니터링 스크립트
# 사용법: bash scripts/monitor-teams.sh <organization> <팀수>
# 예시:   bash scripts/monitor-teams.sh multi9-project1 3
#
# 기능:
#   - 각 팀 레포의 최근 커밋 활동 확인
#   - 팀원별 커밋 수 확인
#   - DEVLOG 변경사항 요약
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

if [ -z "$1" ] || [ -z "$2" ]; then
    echo -e "${RED}❌ 사용법: bash scripts/monitor-teams.sh <organization> <팀수>${NC}"
    echo "예시: bash scripts/monitor-teams.sh multi9-project1 3"
    exit 1
fi

ORG_NAME="$1"
TEAM_COUNT="$2"

if ! command -v gh &> /dev/null; then
    echo -e "${RED}❌ GitHub CLI(gh)가 필요합니다: https://cli.github.com/${NC}"
    exit 1
fi

echo ""
echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  📊 팀 활동 모니터링 — ${ORG_NAME}${NC}"
echo -e "${CYAN}  $(date '+%Y-%m-%d %H:%M')${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════${NC}"

for i in $(seq 1 "$TEAM_COUNT"); do
    REPO="${ORG_NAME}/team${i}-project"

    echo ""
    echo -e "${YELLOW}──────────────────────────────────────${NC}"
    echo -e "${BOLD}🏷️  Team ${i}${NC} — ${REPO}"
    echo -e "${YELLOW}──────────────────────────────────────${NC}"

    # 레포 존재 확인
    if ! gh repo view "$REPO" &> /dev/null 2>&1; then
        echo -e "  ${RED}레포를 찾을 수 없습니다${NC}"
        continue
    fi

    # 등록된 멤버 확인 (members/ 하위 디렉토리)
    echo -e "  ${GREEN}👥 등록된 멤버:${NC}"
    MEMBERS=$(gh api "repos/${REPO}/contents/members" --jq '.[].name' 2>/dev/null || echo "")
    if [ -n "$MEMBERS" ]; then
        echo "$MEMBERS" | while read -r name; do
            if [ "$name" != "_template" ]; then
                echo "     - $name"
            fi
        done
    else
        echo "     (멤버 없음 또는 조회 실패)"
    fi

    # 최근 커밋 5개
    echo ""
    echo -e "  ${GREEN}📝 최근 커밋 (5개):${NC}"
    gh api "repos/${REPO}/commits?per_page=5" \
        --jq '.[] | "     \(.commit.author.date | split("T")[0]) | \(.author.login // .commit.author.name) | \(.commit.message | split("\n")[0])"' \
        2>/dev/null || echo "     (조회 실패)"

    # 커미터별 커밋 수 (최근 30개 기준)
    echo ""
    echo -e "  ${GREEN}📊 커미터별 활동 (최근 30커밋):${NC}"
    gh api "repos/${REPO}/commits?per_page=30" \
        --jq '[.[].author.login // .[].commit.author.name] | group_by(.) | map({name: .[0], count: length}) | sort_by(-.count) | .[] | "     \(.name): \(.count)회"' \
        2>/dev/null || echo "     (조회 실패)"

done

echo ""
echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ 모니터링 완료${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
