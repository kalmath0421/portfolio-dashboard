#!/bin/bash
# NAS 인스턴스 업데이트 스크립트.
#
# 사용:
#   sudo bash /volume1/docker/update.sh portfolio-dashboard
#   sudo bash /volume1/docker/update.sh portfolio-dashboard-aran
#
# 또는 한 번에 둘 다:
#   sudo bash /volume1/docker/update.sh all
#
# 매번 wget 4줄 + tar + cp + docker compose up 을 수동으로 치는 부담을 없앰.
set -euo pipefail

REPO_TARBALL="https://github.com/kalmath0421/portfolio-dashboard/archive/refs/heads/main.tar.gz"
BASE_DIR="/volume1/docker"

update_one() {
    local instance="$1"
    local dir="$BASE_DIR/$instance"
    if [ ! -d "$dir" ]; then
        echo "❌ $dir 폴더가 없습니다."
        return 1
    fi
    echo "🔄 $instance 업데이트 시작..."
    cd "$dir"
    wget -q "$REPO_TARBALL" -O /tmp/update.tar.gz
    tar -xzf /tmp/update.tar.gz --strip-components=1
    # 아란 인스턴스는 docker-compose.aran.yml 을 메인 compose 로 사용
    if [ "$instance" = "portfolio-dashboard-aran" ]; then
        cp docker-compose.aran.yml docker-compose.yml
    fi
    docker compose up -d --build
    echo "✅ $instance 업데이트 완료"
}

case "${1:-}" in
    portfolio-dashboard|portfolio-dashboard-aran)
        update_one "$1"
        ;;
    all)
        update_one "portfolio-dashboard"
        update_one "portfolio-dashboard-aran"
        ;;
    *)
        echo "사용법: sudo bash $0 <portfolio-dashboard|portfolio-dashboard-aran|all>"
        exit 1
        ;;
esac
